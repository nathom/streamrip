import asyncio
import base64
import json
import logging
import re
import time
import hashlib # For jitter in retry
from json import JSONDecodeError

import aiohttp

from ..config import Config
from ..exceptions import (
    APIError,
    APILimitError,
    AuthenticationError,
    ClientError,
    InvalidAPIResponseError,
    MissingCredentialsError,
    NetworkError,
    NonStreamableError,
    ResourceNotFoundError,
    TidalAPIError,
)
from .client import Client
from .downloadable import TidalDownloadable

logger = logging.getLogger("streamrip")

BASE = "https://api.tidalhifi.com/v1"
AUTH_URL = "https://auth.tidal.com/v1/oauth2"

CLIENT_ID = base64.b64decode("elU0WEhWVmtjMnREUG80dA==").decode("iso-8859-1")
CLIENT_SECRET = base64.b64decode(
    "VkpLaERGcUpQcXZzUFZOQlY2dWtYVEptd2x2YnR0UDd3bE1scmM3MnNlND0=",
).decode("iso-8859-1")
AUTH = aiohttp.BasicAuth(login=CLIENT_ID, password=CLIENT_SECRET)
STREAM_URL_REGEX = re.compile(
    r"#EXT-X-STREAM-INF:BANDWIDTH=\d+,AVERAGE-BANDWIDTH=\d+,CODECS=\"(?!jpeg)[^\"]+\",RESOLUTION=\d+x\d+\n(.+)"
)

QUALITY_MAP = {
    0: "LOW",  # AAC
    1: "HIGH",  # AAC
    2: "LOSSLESS",  # CD Quality
    3: "HI_RES",  # MQA
}


class TidalClient(Client):
    """TidalClient."""

    source = "tidal"
    max_quality = 3

    def __init__(self, config: Config):
        self.logged_in = False
        self.global_config = config
        self.config = config.session.tidal
        self.rate_limiter = self.get_rate_limiter(
            config.session.downloads.requests_per_minute,
        )
        self.max_retries = 3
        self.initial_retry_delay = 1.0

    async def login(self):
        try:
            self.session = await self.get_session(
                verify_ssl=self.global_config.session.downloads.verify_ssl
            )
        except Exception as e:
            raise ClientError(f"Falha ao inicializar a sessão HTTP para Tidal: {e}") from e

        c = self.config
        if not c.access_token:
            raise MissingCredentialsError("Token de acesso do Tidal não encontrado na configuração.")
        if not c.refresh_token:
            # While not strictly needed for login if access token is valid,
            # it's crucial for maintaining the session.
            logger.warning("Refresh token do Tidal não encontrado. A sessão pode expirar permanentemente.")
        if not c.token_expiry:
             raise MissingCredentialsError("Data de expiração do token do Tidal não encontrada na configuração.")


        try:
            self.token_expiry = float(c.token_expiry)
        except ValueError:
            raise ClientError("Data de expiração do token do Tidal inválida na configuração.")

        self.refresh_token = c.refresh_token

        try:
            # Check if token needs refresh (e.g., expires in less than 1 day)
            if self.token_expiry - time.time() < 86400:  # 1 day
                logger.info("Token de acesso do Tidal expirando em breve ou expirado. Tentando atualizar...")
                await self._refresh_access_token()
            else:
                # Validate existing access token by trying to use it
                logger.info("Validando token de acesso existente do Tidal...")
                await self._login_by_access_token(c.access_token, c.user_id)
        except MissingCredentialsError: # Propagate if refresh token is missing during refresh
            raise
        except (NetworkError, TidalAPIError, AuthenticationError) as e:
            logger.error(f"Falha ao validar/atualizar token do Tidal: {e}. Tentando atualizar token como último recurso se não foi tentado.")
            # If initial validation failed, try a refresh if not already done
            if not (self.token_expiry - time.time() < 86400): # i.e. if refresh wasn't the primary path
                try:
                    await self._refresh_access_token()
                except Exception as refresh_e:
                    raise AuthenticationError(f"Falha ao atualizar o token de acesso do Tidal após falha de validação: {refresh_e}") from refresh_e
            else:
                raise AuthenticationError(f"Falha ao validar/atualizar token do Tidal: {e}") from e
        except Exception as e: # Catch any other unexpected error during login/refresh
            raise AuthenticationError(f"Erro inesperado durante o processo de login/atualização do Tidal: {e}") from e


        self.logged_in = True
        logger.info("Login no Tidal bem-sucedido.")

    async def get_metadata(self, item_id: str, media_type: str) -> dict:
        """Send a request to the api for information.

        :param item_id:
        :type item_id: str
        :param media_type: track, album, playlist, or video.
        :type media_type: str
        :rtype: dict
        """
        assert media_type in (
            "track",
            "album",
            "playlist",
            "video",
            "artist",
        ), f"Tipo de mídia inválido: {media_type}"

        url_path_segment = f"{media_type}s/{item_id}"

        # Initial metadata request for the main item
        item_data = await self._api_request(url_path_segment)

        if media_type in ("playlist", "album"):
            # Fetch tracks for playlist or album
            tracks_url = f"{url_path_segment}/items"

            # Initial fetch for the first batch of tracks
            try:
                tracks_resp = await self._api_request(tracks_url)
                if not isinstance(tracks_resp, dict) or "items" not in tracks_resp:
                    raise InvalidAPIResponseError(f"Resposta de itens de {media_type} inválida para {item_id}.", item=item_id)

                all_track_items = tracks_resp["items"]
                total_tracks = tracks_resp.get("totalNumberOfItems", item_data.get("numberOfTracks", len(all_track_items)))

                # Paginate if necessary
                # Tidal API limit for /items is usually 100
                offset = len(all_track_items)
                page_limit = tracks_resp.get("limit", 100)

                while offset < total_tracks:
                    logger.debug(f"Buscando mais faixas para {media_type} {item_id}: offset={offset}, limit={page_limit}")
                    paginated_tracks_resp = await self._api_request(tracks_url, params={"offset": offset, "limit": page_limit})
                    if not isinstance(paginated_tracks_resp, dict) or "items" not in paginated_tracks_resp:
                        logger.warning(f"Resposta de paginação de itens de {media_type} inválida para {item_id} no offset {offset}.")
                        break # Stop pagination on invalid response

                    paginated_items = paginated_tracks_resp["items"]
                    if not paginated_items: # No more items returned
                        break
                    all_track_items.extend(paginated_items)
                    offset += len(paginated_items)
                    if len(paginated_items) < page_limit: # API returned fewer than limit, must be the end
                        break

                # Structure can vary slightly; some responses nest item under 'item' key
                item_data["tracks"] = [ti.get("item", ti) for ti in all_track_items]

            except (ResourceNotFoundError, InvalidAPIResponseError) as e:
                logger.warning(f"Não foi possível buscar faixas para {media_type} {item_id}: {e}")
                item_data["tracks"] = [] # Ensure 'tracks' key exists even if fetching failed

        elif media_type == "artist":
            logger.debug(f"Buscando álbuns e EPs/singles para o artista {item_id}")
            try:
                albums_url = f"{url_path_segment}/albums"
                # Fetch regular albums and EPs/Singles concurrently
                album_resp, ep_resp = await asyncio.gather(
                    self._api_request(albums_url),
                    self._api_request(albums_url, params={"filter": "EPSANDSINGLES"}),
                    return_exceptions=True # Handle errors for individual calls
                )

                combined_albums = []
                if isinstance(album_resp, dict) and "items" in album_resp:
                    combined_albums.extend(album_resp["items"])
                elif isinstance(album_resp, Exception):
                    logger.warning(f"Erro ao buscar álbuns para o artista {item_id}: {album_resp}")

                if isinstance(ep_resp, dict) and "items" in ep_resp:
                    combined_albums.extend(ep_resp["items"])
                elif isinstance(ep_resp, Exception):
                     logger.warning(f"Erro ao buscar EPs/Singles para o artista {item_id}: {ep_resp}")

                item_data["albums"] = combined_albums
            except Exception as e: # Catch any other error during artist album fetching
                logger.error(f"Falha geral ao buscar discografia do artista {item_id}: {e}", exc_info=True)
                item_data["albums"] = []


        elif media_type == "track":
            try:
                lyrics_resp = await self._api_request(
                    f"tracks/{item_id}/lyrics", base="https://listen.tidal.com/v1"
                )

                if not isinstance(lyrics_resp, dict):
                     raise InvalidAPIResponseError(f"Resposta de letras inválida para faixa {item_id}", item=item_id)

                # Use unsynced lyrics for MP3, synced for others (FLAC, OPUS, etc)
                use_mp3_format = (
                    self.global_config.session.conversion.enabled and
                    self.global_config.session.conversion.codec.upper() == "MP3"
                )
                if use_mp3_format:
                    item_data["lyrics"] = lyrics_resp.get("lyrics", "")
                else:
                    item_data["lyrics"] = lyrics_resp.get("subtitles") or lyrics_resp.get("lyrics", "")
            except ResourceNotFoundError:
                logger.debug(f"Nenhuma letra encontrada para a faixa {item_id}")
                item_data["lyrics"] = ""
            except (TidalAPIError, InvalidAPIResponseError) as e: # Catch API or response errors for lyrics
                logger.warning(f"Falha ao obter letras para a faixa {item_id}: {e}")
                item_data["lyrics"] = ""
            except Exception as e: # Catch any other unexpected error
                logger.error(f"Erro inesperado ao buscar letras para a faixa {item_id}: {e}", exc_info=True)
                item_data["lyrics"] = ""


        logger.debug(f"Metadados para {media_type} {item_id}: {item_data}")
        return item_data

    async def search(self, media_type: str, query: str, limit: int = 100) -> list[dict]:
        """Search for a query.

        :param query:
        :type query: str
        :param media_type: track, album, playlist, or video.
        :type media_type: str
        :param limit: max is 100
        :type limit: int
        :rtype: dict
        """
        params = {
            "query": query,
            "limit": limit, # Tidal's API typically caps limit at 50 for search
        }
        if media_type not in ("album", "track", "playlist", "video", "artist"):
            raise TidalAPIError(f"Tipo de mídia '{media_type}' inválido para pesquisa no Tidal.")

        # Tidal search results are directly under `items` for each media type category
        # e.g. resp -> {"artists": {"items": [...]}, "albums": {"items": [...]}}
        # The original code was returning [resp] which might not be what's intended.
        # It should return a list of pages, where each page is a dict of items.
        # For search, it usually returns one "page" (response dict) containing all categories.

        resp_data = await self._api_request(f"search", params={"query": query, "types": media_type.upper() + "S", "limit": limit})

        # The response structure for search is {'albums': {'items': [], ...}, 'tracks': ...}
        # We need to extract items for the specific media_type requested.
        # For simplicity, if the API call is search/{media_type}s, it directly returns items for that type.
        # The current _api_request structure would hit search/albums, search/tracks etc.

        # Assuming the original structure where _api_request(f"search/{media_type}s") is used:
        # This would mean the response `resp` is already the content of e.g. resp['albums']
        # If `resp_data` is from `search?types=ALBUMS`, then `resp_data` is `{'albums': {'items': [...]}}`
        # Let's adjust to how it was likely intended:

        search_path = f"search/{media_type}s" # e.g. search/albums, search/tracks
        resp_items_focused = await self._api_request(search_path, params=params)

        if not isinstance(resp_items_focused, dict) or "items" not in resp_items_focused:
            logger.warning(f"Resposta de pesquisa inesperada para {media_type} com query '{query}'.")
            return [] # Return empty list if items are not found as expected

        # The original code returned [resp] if len(resp["items"]) > 1.
        # This seems to imply it expects a list of pages, but search usually returns one comprehensive page.
        # Returning the direct list of items seems more standard for a search function.
        # If the goal is to match `QobuzClient.search` which returns list[dict] (list of pages),
        # then we wrap the single response dict in a list if it contains items.
        if resp_items_focused["items"]:
            return [resp_items_focused] # Return as a single page in a list
        return []


    async def get_downloadable(self, track_id: str, quality: int):
        params = {
            "audioquality": QUALITY_MAP[quality],
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
        }
        # Map our quality to Tidal's internal quality strings if not already done by caller
        # Assuming QUALITY_MAP is {0: "LOW", 1: "HIGH", 2: "LOSSLESS", 3: "HI_RES"}
        # And `quality` param is an int 0-3.

        if quality not in QUALITY_MAP:
            raise ValueError(f"Qualidade inválida para Tidal: {quality}. Valores válidos: {list(QUALITY_MAP.keys())}")

        params["audioquality"] = QUALITY_MAP[quality]

        try:
            resp_data = await self._api_request(
                f"tracks/{track_id}/playbackinfopostpaywall", params
            )
        except ResourceNotFoundError: # if _api_request raises 404 as ResourceNotFoundError
             logger.warning(f"Faixa {track_id} não encontrada para obter informações de playback (playbackinfopostpaywall).")
             raise NonStreamableError(f"Faixa {track_id} não encontrada (playbackinfo).", item=track_id)

        logger.debug(f"Playback info for track {track_id}: {resp_data}")

        if not isinstance(resp_data, dict):
            raise InvalidAPIResponseError(f"Resposta de playbackinfo inesperada para faixa {track_id}.", item=track_id)

        manifest_b64 = resp_data.get("manifest")
        if not manifest_b64:
            user_message = resp_data.get("userMessage")
            if user_message:
                raise NonStreamableError(f"Não foi possível obter o manifesto de stream para a faixa {track_id}: {user_message}", item=track_id)
            # Attempt to retry with lower quality if manifest is missing and no specific user message
            # This was the original behavior for JSONDecodeError, adapt it here.
            if quality > 0: # Check if there's a lower quality to try
                logger.warning(
                    f"Falha ao obter manifesto para faixa {track_id} com qualidade {QUALITY_MAP[quality]}. "
                    f"Tentando com qualidade inferior."
                )
                return await self.get_downloadable(track_id, quality - 1)
            raise InvalidAPIResponseError(f"Manifesto de stream não encontrado na resposta para a faixa {track_id}.", item=track_id)

        try:
            manifest_json = base64.b64decode(manifest_b64).decode("utf-8")
            manifest = json.loads(manifest_json)
        except (TypeError, ValueError, JSONDecodeError) as e:
            # This was the original retry trigger, now more explicit
            if quality > 0:
                logger.warning(
                    f"Falha ao decodificar manifesto para faixa {track_id} (qualidade: {QUALITY_MAP[quality]}): {e}. "
                    f"Tentando com qualidade inferior."
                )
                return await self.get_downloadable(track_id, quality - 1)
            raise InvalidAPIResponseError(f"Falha ao decodificar o manifesto de stream para a faixa {track_id}: {e}", item=track_id) from e


        logger.debug(f"Manifest for track {track_id}: {manifest}")

        if not isinstance(manifest, dict) or not manifest.get("urls"):
            raise InvalidAPIResponseError(f"Conteúdo do manifesto inválido ou URLs de stream ausentes para faixa {track_id}.", item=track_id)

        enc_key = manifest.get("keyId")
        if manifest.get("encryptionType", "").upper() == "NONE":
            enc_key = None

        return TidalDownloadable(
            session=self.session, # Ensure session is passed
            url=manifest["urls"][0], # Assuming first URL is the one to use
            codec=manifest.get("codecs", "unknown"), # Provide default if missing
            encryption_key=enc_key,
            restrictions=manifest.get("restrictions")
        )

    async def get_video_file_url(self, video_id: str) -> str:
        """Get the HLS video stream url.

        The stream is downloaded using ffmpeg for now.

        :param video_id:
        :type video_id: str
        :rtype: str
        """
        params = {
            "videoquality": "HIGH",
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
        }

        resp_data = await self._api_request(
            f"videos/{video_id}/playbackinfopostpaywall", params=params
        )

        if not isinstance(resp_data, dict) or not resp_data.get("manifest"):
            raise InvalidAPIResponseError(f"Resposta de playbackinfo de vídeo inválida para ID {video_id}.", item=video_id)

        try:
            manifest_json = base64.b64decode(resp_data["manifest"]).decode("utf-8")
            manifest = json.loads(manifest_json)
        except (TypeError, ValueError, JSONDecodeError) as e:
            raise InvalidAPIResponseError(f"Falha ao decodificar manifesto de vídeo para ID {video_id}: {e}", item=video_id) from e

        if not isinstance(manifest, dict) or not manifest.get("urls"):
            raise InvalidAPIResponseError(f"Conteúdo do manifesto de vídeo inválido ou URLs ausentes para ID {video_id}.", item=video_id)

        # The original code fetched another JSON from manifest["urls"][0]
        # This implies manifest["urls"][0] is a URL to another manifest (e.g., HLS master playlist)
        master_playlist_url = manifest["urls"][0]

        try:
            async with self.session.get(master_playlist_url) as hls_resp:
                hls_resp.raise_for_status() # Check for HTTP errors
                hls_master_playlist_text = await hls_resp.text()
        except aiohttp.ClientError as e:
            raise NetworkError(f"Erro de rede ao buscar o master playlist HLS para vídeo {video_id} de {master_playlist_url}: {e}", item=video_id) from e

        # The original code used `available_urls.json()` then `available_urls.text` which is confusing.
        # Assuming HLS master playlist is text.

        matches = list(STREAM_URL_REGEX.finditer(hls_master_playlist_text))
        if not matches:
            raise InvalidAPIResponseError(f"Nenhuma URL de stream de vídeo encontrada no master playlist HLS para vídeo {video_id}.", item=video_id)

        # Highest resolution is assumed to be last by original code
        return matches[-1].group(1)


    # ---------- Login Utilities ---------------

    async def _login_by_access_token(self, token: str, user_id_from_config: str | None):
        """
        Validates an access token by fetching session info.
        Updates config if successful.
        """
        headers = {"authorization": f"Bearer {token}"}
        # Using _api_request for retries and error handling consistency,
        # but it adds countryCode etc. which is not needed for /sessions.
        # For /sessions, a direct call is cleaner.
        try:
            async with self.session.get(
                "https://api.tidal.com/v1/sessions", headers=headers
            ) as http_resp:
                # http_resp.raise_for_status() # This would raise for 401, which we want to handle
                if http_resp.status == 401: # Unauthorized, token likely invalid/expired
                    raise AuthenticationError("Token de acesso do Tidal inválido ou expirado ao verificar sessão.", item=user_id_from_config)

                http_resp.raise_for_status() # For other HTTP errors (5xx etc.)
                resp_data = await http_resp.json()

        except aiohttp.ClientError as e:
            raise NetworkError(f"Erro de rede ao verificar sessão do Tidal: {e}", item=user_id_from_config) from e
        except JSONDecodeError as e:
            raise InvalidAPIResponseError(f"Resposta de sessão do Tidal inválida (não JSON).", item=user_id_from_config) from e


        if not isinstance(resp_data, dict):
             raise InvalidAPIResponseError("Resposta de sessão do Tidal inesperada.", item=user_id_from_config)

        # Original code checked resp.get("status", 200) != 200
        # raise_for_status() handles HTTP errors, but we might get a 200 with an internal error status.
        # Tidal's /sessions usually just returns user data on success or HTTP error.

        api_user_id = resp_data.get("userId")
        if api_user_id is None:
            raise InvalidAPIResponseError("ID do usuário não encontrado na resposta da sessão do Tidal.", item=user_id_from_config)

        # If user_id_from_config was provided (e.g. from initial OAuth), verify it matches.
        # If not provided (e.g. loading from existing config), this check is skipped.
        if user_id_from_config and str(api_user_id) != str(user_id_from_config):
            raise AuthenticationError(
                f"ID de usuário da API do Tidal ({api_user_id}) não corresponde ao ID configurado ({user_id_from_config})."
            )

        c = self.config
        c.user_id = str(api_user_id) # Ensure it's string
        c.country_code = resp_data.get("countryCode")
        if not c.country_code:
             logger.warning("Código do país não encontrado na resposta da sessão do Tidal.")
        c.access_token = token # Token is confirmed valid
        self.global_config.file.set_modified() # Mark main config as modified to save changes
        self._update_authorization_header()


    async def _get_login_link(self) -> tuple[str, str]: # Returns (verification_uri_complete, device_code)
        data = {
            "client_id": CLIENT_ID,
            "scope": "r_usr+w_usr+w_sub",
        }
        # This is part of OAuth device flow, doesn't use existing auth headers
        # Use _api_post_direct for this as it doesn't add auth/countryCode
        resp_data = await self._api_post_direct(f"{AUTH_URL}/device_authorization", data)

        # _api_post_direct already checks for non-200 status and raises TidalAPIError
        # It also handles JSON decoding and NetworkError.

        if not isinstance(resp_data, dict): # Should be caught by _api_post_direct if not JSON
            raise InvalidAPIResponseError("Resposta de autorização de dispositivo Tidal inválida.")

        device_code = resp_data.get("deviceCode")
        verification_uri = resp_data.get("verificationUriComplete")
        user_code = resp_data.get("userCode") # Also useful to display

        if not device_code or not verification_uri or not user_code:
            raise InvalidAPIResponseError("deviceCode, verificationUriComplete ou userCode ausente na resposta de autorização do dispositivo Tidal.")

        # The original returned f"https://{device_code}" - this seems incorrect.
        # verificationUriComplete is the URL user should visit.
        # userCode is what they enter at that URL.
        # deviceCode is used internally to poll for auth status.
        logger.info(f"Para autorizar o Tidal, visite: {verification_uri} e insira o código: {user_code}")
        return verification_uri, device_code


    def _update_authorization_header(self):
        if self.session and self.config.access_token:
            self.session.headers.update(
                {"authorization": f"Bearer {self.config.access_token}"}
            )
        elif self.session: # Clear if no token
             if "authorization" in self.session.headers:
                del self.session.headers["authorization"]


    async def _poll_for_authorization(self, device_code: str) -> dict:
        """Polls the token endpoint to see if user authorized via device code."""
        data = {
            "client_id": CLIENT_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "scope": "r_usr+w_usr+w_sub",
        }

        # Polling loop - this should be managed by the prompter usually
        # For now, just one attempt for _get_auth_status equivalent
        # The prompter would call this repeatedly.

        # Using _api_post_direct as it's an OAuth endpoint not requiring prior session auth
        resp_data = await self._api_post_direct(f"{AUTH_URL}/token", data, auth=AUTH)

        # _api_post_direct raises TidalAPIError for non-200,
        # but OAuth has specific error codes in the body for 400.
        # If resp_data contains "error":"authorization_pending", it's not an error yet.
        if isinstance(resp_data, dict) and resp_data.get("error") == "authorization_pending":
            # This status means user hasn't completed auth yet.
            # In a real polling scenario, we'd wait and retry.
            # For a single check, this is equivalent to status 2 (pending) in original.
            raise TidalAPIError("Autorização pendente. O usuário ainda não concluiu o login no navegador.")

        # If no 'error' key and it's a 200 (checked by _api_post_direct), assume success.
        if not isinstance(resp_data, dict) or "access_token" not in resp_data:
            raise InvalidAPIResponseError("Resposta de token OAuth inválida ou token de acesso ausente.", item=device_code)

        auth_info = {
            "user_id": resp_data.get("user", {}).get("userId"),
            "country_code": resp_data.get("user", {}).get("countryCode"),
            "access_token": resp_data["access_token"],
            "refresh_token": resp_data.get("refresh_token"),
            "token_expiry": float(resp_data.get("expires_in", 0)) + time.time(),
        }
        if not auth_info["user_id"] or not auth_info["refresh_token"]:
             raise InvalidAPIResponseError("UserID ou refresh_token ausente na resposta de token OAuth do Tidal.", item=device_code)

        return auth_info


    async def _refresh_access_token(self):
        """Refreshes the access token."""
        if not self.refresh_token:
            raise MissingCredentialsError("Refresh token do Tidal não disponível para atualizar o token de acesso.")

        data = {
            "client_id": CLIENT_ID,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
            "scope": "r_usr+w_usr+w_sub",
        }
        # OAuth token endpoint uses BasicAuth with client_id/secret
        resp_data = await self._api_post_direct(f"{AUTH_URL}/token", data, auth=AUTH)

        # _api_post_direct raises TidalAPIError for non-200 (e.g. invalid refresh token -> 400/401)
        # It also handles JSON and NetworkError.

        if not isinstance(resp_data, dict) or "access_token" not in resp_data:
            raise InvalidAPIResponseError("Token de acesso ausente na resposta de atualização do Tidal.", item=self.refresh_token)

        c = self.config
        c.access_token = resp_data["access_token"]
        # Refresh token might also be updated by Tidal, though not always
        if "refresh_token" in resp_data:
             c.refresh_token = resp_data["refresh_token"]
        c.token_expiry = str(float(resp_data.get("expires_in", 0)) + time.time())
        self.global_config.file.set_modified()
        self._update_authorization_header()
        self.token_expiry = float(c.token_expiry) # Update in-memory expiry
        logger.info("Token de acesso do Tidal atualizado com sucesso.")


    # ---------- API Request Utilities (with retry) ---------------

    async def _api_post_direct(self, url: str, data: dict, auth: aiohttp.BasicAuth | None = None) -> dict:
        """
        Direct POST request with retry logic, without adding default params like countryCode.
        Used for OAuth flows.
        """
        current_retry = 0
        while True:
            logger.debug("api_post_direct: url=%s, data=%s, attempt=%d", url, data, current_retry + 1)
            try:
                async with self.rate_limiter: # Should this apply to OAuth endpoints? Usually they have own limits.
                    async with self.session.post(url, data=data, auth=auth) as http_resp:
                        try:
                            resp_data = await http_resp.json()
                        except JSONDecodeError:
                            resp_text = await http_resp.text()
                            # For OAuth, 400 errors often have useful info in body but might not be JSON
                            if http_resp.status == 400 and "error" in resp_text.lower():
                                # Try to parse as form-urlencoded or simple error string
                                error_description = re.search(r'error_description":"([^"]+)"', resp_text)
                                if error_description:
                                    resp_data = {"error": "oauth_error", "error_description": error_description.group(1)}
                                else:
                                    resp_data = {"error": "oauth_error", "message": resp_text[:200]}
                            else:
                                resp_data = {"error": "invalid_response", "message": resp_text[:200]}
                            logger.warning(
                                f"Resposta não-JSON (ou erro OAuth não-JSON) de {url} (status {http_resp.status}): {resp_text[:100]}"
                            )

                        # Handle OAuth specific 400 errors that are not "authorization_pending"
                        if http_resp.status == 400 and resp_data.get("error") != "authorization_pending":
                            error_msg = resp_data.get("error_description") or resp_data.get("error") or resp_data.get("message", "Erro OAuth 400 desconhecido.")
                            raise TidalAPIError(f"Erro OAuth do Tidal: {error_msg} (url: {url})", item=data.get("device_code"))

                        # For other non-200 statuses for OAuth, raise generic TidalAPIError
                        if http_resp.status != 200 and resp_data.get("error") != "authorization_pending":
                            error_msg = resp_data.get("message", f"Erro na solicitação OAuth do Tidal (status: {http_resp.status}) para {url}.")
                            raise TidalAPIError(error_msg, item=data.get("device_code"))

                        # Log non-200s that are not pending authorization for debugging
                        if http_resp.status != 200 and resp_data.get("error") != "authorization_pending":
                             logger.debug(f"OAuth Tidal {url} respondeu com status {http_resp.status}. Data: {data}. Resposta: {resp_data}")

                        return resp_data # Includes pending authorization responses

            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError, aiohttp.ClientOSError) as e:
                logger.warning(f"Erro de conexão/rede com OAuth Tidal ({url}): {e}. Tentativa {current_retry + 1}/{self.max_retries}")
                if current_retry < self.max_retries:
                    await asyncio.sleep(self.initial_retry_delay * (2**current_retry))
                    current_retry += 1
                    continue
                raise NetworkError(f"Erro de conexão com OAuth Tidal ({url}) após {self.max_retries} tentativas: {e}") from e
            except asyncio.TimeoutError as e:
                logger.warning(f"Timeout ao conectar com OAuth Tidal ({url}). Tentativa {current_retry + 1}/{self.max_retries}")
                if current_retry < self.max_retries:
                    await asyncio.sleep(self.initial_retry_delay * (2**current_retry))
                    current_retry += 1
                    continue
                raise NetworkError(f"Timeout ao conectar com OAuth Tidal ({url}) após {self.max_retries} tentativas.") from e
            except aiohttp.ClientError as e:
                raise NetworkError(f"Erro de cliente HTTP com OAuth Tidal ({url}): {e}") from e


    async def _api_request(self, path: str, params: dict | None = None, base: str = BASE) -> dict:
        """Handles authenticated Tidal API requests with retry logic."""
        if not self.logged_in or not self.config.access_token:
            # This should ideally be checked before calling methods requiring auth
            raise AuthenticationError("Não está logado no Tidal ou token de acesso ausente para solicitação à API.")

        current_params = {"countryCode": self.config.country_code, "limit": 100}
        if params:
            current_params.update(params)

        url = f"{base}/{path}"
        item_id_for_logging = current_params.get(f"{path.split('/')[0][:-1]}Id") # e.g. trackId from tracks/trackId

        current_retry = 0
        while True:
            logger.debug("_api_request: url=%s, params=%s, attempt=%d", url, current_params, current_retry + 1)
            try:
                async with self.rate_limiter:
                    async with self.session.get(url, params=current_params) as http_resp:
                        try:
                            resp_data = await http_resp.json()
                        except JSONDecodeError:
                            resp_text = await http_resp.text()
                            resp_data = {"message": resp_text[:200]} # Fallback for non-JSON
                            logger.warning(
                                f"Resposta não-JSON da API Tidal para {path} (status {http_resp.status}): {resp_text[:100]}"
                            )

                        if http_resp.status == 401: # Unauthorized, token likely expired
                            logger.warning(f"Token de acesso Tidal não autorizado (401) para {path}. Tentando atualizar...")
                            try:
                                await self._refresh_access_token()
                                # After successful refresh, retry the original request (once)
                                if current_retry == 0: # Only retry token refresh once automatically
                                     current_retry +=1 # Count as a retry attempt
                                     logger.info(f"Token atualizado. Tentando novamente solicitação para {path}.")
                                     continue
                                else: # Already tried refreshing
                                     raise AuthenticationError(f"Falha na autenticação para {path} mesmo após tentativa de atualização do token.")
                            except Exception as refresh_e:
                                raise AuthenticationError(f"Falha ao atualizar token Tidal após erro 401 em {path}: {refresh_e}") from refresh_e

                        if http_resp.status == 404:
                            raise ResourceNotFoundError(f"Recurso Tidal não encontrado: {path} com params {current_params}", item=item_id_for_logging)

                        if http_resp.status == 429: # Rate limit
                            delay = (self.initial_retry_delay * (2**current_retry)) + (hashlib.md5(str(current_params).encode()).digest()[0] / 255.0)
                            logger.warning(
                                f"Limite de taxa da API Tidal atingido para {path} (status 429). "
                                f"Tentando novamente em {delay:.2f}s... (tentativa {current_retry + 1}/{self.max_retries})"
                            )
                            if current_retry < self.max_retries:
                                await asyncio.sleep(delay)
                                current_retry += 1
                                continue
                            raise APILimitError(
                                f"Limite de taxa da API Tidal excedido para {path} após {self.max_retries} tentativas.",
                                item=item_id_for_logging
                            )

                        # For other non-200 client/server errors after potential refresh attempt
                        if http_resp.status >= 400:
                             error_message = resp_data.get("userMessage") or resp_data.get("message", f"Erro da API Tidal {http_resp.status} para {path}")
                             raise TidalAPIError(error_message, item=item_id_for_logging)

                        return resp_data # Successful response

            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError, aiohttp.ClientOSError) as e:
                logger.warning(f"Erro de conexão/rede com API Tidal ({path}): {e}. Tentativa {current_retry + 1}/{self.max_retries}")
                if current_retry < self.max_retries:
                    await asyncio.sleep(self.initial_retry_delay * (2**current_retry))
                    current_retry += 1
                    continue
                raise NetworkError(f"Erro de conexão com API Tidal ({path}) após {self.max_retries} tentativas: {e}", item=item_id_for_logging) from e
            except asyncio.TimeoutError as e:
                logger.warning(f"Timeout ao conectar com API Tidal ({path}). Tentativa {current_retry + 1}/{self.max_retries}")
                if current_retry < self.max_retries:
                    await asyncio.sleep(self.initial_retry_delay * (2**current_retry))
                    current_retry += 1
                    continue
                raise NetworkError(f"Timeout ao conectar com API Tidal ({path}) após {self.max_retries} tentativas.", item=item_id_for_logging) from e
            except aiohttp.ClientError as e: # Catch other aiohttp client errors
                raise NetworkError(f"Erro de cliente HTTP com API Tidal ({path}): {e}", item=item_id_for_logging) from e
