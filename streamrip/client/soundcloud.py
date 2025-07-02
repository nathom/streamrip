import asyncio
import itertools
import logging
import random
import re
import hashlib # For jitter in retry

import aiohttp # For client errors

from ..config import Config
from ..exceptions import (
    ClientError, # Base for client-related issues
    NetworkError, # For network connectivity problems
    SoundcloudAPIError, # Specific for SoundCloud API errors not covered by others
    InvalidAPIResponseError, # For unexpected API response structure
    ResourceNotFoundError, # For 404 errors
    NonStreamableError, # For tracks that cannot be streamed
    APILimitError # For 429 errors
)
from .client import Client
from .downloadable import SoundcloudDownloadable

# e.g. 123456-293847-121314-209849
USER_ID = "-".join(str(random.randint(111111, 999999)) for _ in range(4))
BASE = "https://api-v2.soundcloud.com"
STOCK_URL = "https://soundcloud.com/"

# for playlists
MAX_BATCH_SIZE = 50

logger = logging.getLogger("streamrip")


class SoundcloudClient(Client):
    source = "soundcloud"
    logged_in = False # SoundCloud client is stateless regarding user login for public data

    NON_STREAMABLE = "_non_streamable"
    ORIGINAL_DOWNLOAD = "_original_download"
    NOT_RESOLVED = "_not_resolved" # Should ideally not be used if logic is correct

    def __init__(self, config: Config):
        self.global_config = config
        self.config = config.session.soundcloud # Specific Soundcloud config (client_id, app_version)
        self.rate_limiter = self.get_rate_limiter(
            config.session.downloads.requests_per_minute, # Global rate limit
        )
        self.max_retries = 3 # Max retries for network/API limit errors
        self.initial_retry_delay = 1.0 # Initial delay in seconds for retries

    async def login(self):
        """
        "Logs in" to SoundCloud by ensuring valid client_id and app_version are available.
        These are typically scraped and might need refreshing.
        """
        try:
            self.session = await self.get_session(
                verify_ssl=self.global_config.session.downloads.verify_ssl
            )
        except Exception as e: # Broad exception for session creation issues
            raise ClientError(f"Falha ao inicializar a sessão HTTP para SoundCloud: {e}") from e

        client_id, app_version = self.config.client_id, self.config.app_version

        needs_refresh = True
        if client_id and app_version:
            logger.debug("Verificando tokens existentes do SoundCloud...")
            try:
                if await self._announce_success(): # _announce_success now includes retry
                    logger.debug("Tokens existentes do SoundCloud são válidos.")
                    needs_refresh = False
                else: # Announce failed even after retries (e.g. 401 or other persistent error)
                    logger.info("Falha na verificação dos tokens do SoundCloud (anúncio). Forçando atualização.")
            except (NetworkError, SoundcloudAPIError, APILimitError) as e: # Catch specific errors from _announce_success
                logger.warning(f"Erro ao verificar tokens do SoundCloud: {e}. Forçando atualização.")
            # No need for a generic Exception catch here if _announce_success handles its errors well.

        if needs_refresh:
            logger.info("Atualizando tokens do SoundCloud...")
            try:
                client_id, app_version = await self._refresh_tokens() # _refresh_tokens also improved

                # Update config in session and prepare for saving to file
                cs = self.global_config.session.soundcloud
                cf = self.global_config.file.soundcloud

                cs.client_id = client_id
                cs.app_version = app_version
                cf.client_id = client_id
                cf.app_version = app_version
                self.global_config.file.set_modified() # Mark that config file needs saving
                logger.info("Tokens do SoundCloud atualizados e salvos com sucesso.")
            except (NetworkError, SoundcloudAPIError) as e:
                raise SoundcloudAPIError(f"Falha crítica ao atualizar tokens do SoundCloud: {e}") from e
            except Exception as e: # Catch any other unexpected error from scraping
                raise SoundcloudAPIError(f"Erro inesperado e crítico ao atualizar tokens do SoundCloud: {e}") from e

        # Ensure in-memory config for the current client instance is also up-to-date
        self.config.client_id = client_id
        self.config.app_version = app_version

        logger.debug(f"SoundCloud client_id={client_id}, app_version={app_version}")
        self.logged_in = True # Mark as "logged_in" meaning client_id is ready

    async def get_metadata(self, item_id: str, media_type: str) -> dict:
        if media_type == "track":
            actual_item_id, _ = item_id.split("|", 1) if "|" in item_id else (item_id, None)
            if not actual_item_id or not actual_item_id.isdigit(): # Basic validation
                raise InvalidAPIResponseError(f"ID de faixa SoundCloud inválido: {item_id}", item=item_id)
            return await self._get_track(actual_item_id)
        elif media_type == "playlist":
            if not item_id.isdigit(): # Basic validation for playlist ID
                 raise InvalidAPIResponseError(f"ID de playlist SoundCloud inválido: {item_id}", item=item_id)
            return await self._get_playlist(item_id)
        else:
            raise SoundcloudAPIError(f"Tipo de mídia '{media_type}' não suportado pelo SoundCloud.", item=media_type)

    async def search(
        self,
        media_type: str,
        query: str,
        limit: int = 50, # SoundCloud API default is often lower, e.g., 10 or 20 for search
        offset: int = 0,
    ) -> list[dict]:
        if media_type not in ("track", "playlist"):
            raise SoundcloudAPIError(f"Não é possível pesquisar por '{media_type}' no SoundCloud.", item=media_type)

        params = {
            "q": query,
            "facet": "genre",
            "user_id": USER_ID,
            "limit": limit,
            "offset": offset,
            "linked_partitioning": "1",
        }

        # Path is search/tracks or search/playlists
        resp_data, _ = await self._api_request(f"search/{media_type}s", params=params)

        if not isinstance(resp_data, dict) or "collection" not in resp_data:
            raise InvalidAPIResponseError(
                f"Resposta de pesquisa SoundCloud inválida para {media_type}s: 'collection' ausente.",
                item=query
            )

        collection = resp_data.get("collection")
        if not isinstance(collection, list):
            raise InvalidAPIResponseError(
                f"Campo 'collection' na resposta de pesquisa SoundCloud não é uma lista para {media_type}s.",
                item=query
            )

        processed_collection = []
        for item in collection:
            if not isinstance(item, dict) or "id" not in item:
                logger.warning(f"Item de pesquisa SoundCloud inválido encontrado e ignorado: {item}")
                continue

            if media_type == "track":
                try:
                    item["id"] = self._get_custom_id(item)
                except (SoundcloudAPIError, InvalidAPIResponseError, AssertionError) as e:
                    logger.warning(f"Falha ao gerar ID customizado para a faixa da pesquisa SoundCloud {item.get('id')}: {e}")
                    item_id_val = item.get('id', 'unknown_search_track')
                    item["id"] = f"{item_id_val}|{self.NON_STREAMABLE}"
            processed_collection.append(item)

        resp_data["collection"] = processed_collection

        if processed_collection:
            return [resp_data]
        return []


    async def get_downloadable(self, item_info: str, _: object = None) -> SoundcloudDownloadable:
        logger.debug(f"get_downloadable item_info: {item_info}")

        if not isinstance(item_info, str) or "|" not in item_info:
            raise InvalidAPIResponseError(f"Formato de item_info inválido para SoundCloud: '{item_info}'. Esperado 'id|url_ou_flag'.", item=item_info)

        parts = item_info.split("|", 1)
        item_id, download_info = parts[0], parts[1]

        if not item_id.isdigit():
            raise InvalidAPIResponseError(f"ID de item inválido no item_info do SoundCloud: '{item_id}'.", item=item_info)

        if download_info == self.NON_STREAMABLE:
            raise NonStreamableError(f"Faixa SoundCloud {item_id} marcada como não-streamable.", item=item_id)

        if download_info == self.ORIGINAL_DOWNLOAD:
            resp_data, _ = await self._api_request(f"tracks/{item_id}/download")
            if not isinstance(resp_data, dict) or "redirectUri" not in resp_data:
                raise InvalidAPIResponseError(f"Resposta de download original SoundCloud inválida para faixa {item_id}.", item=item_id)

            return SoundcloudDownloadable(
                self.session,
                {"url": resp_data["redirectUri"], "type": "original"},
            )

        if download_info == self.NOT_RESOLVED:
            logger.error(f"Tentando baixar faixa SoundCloud {item_id} que não foi resolvida corretamente.")
            raise SoundcloudAPIError(f"URL de stream para faixa SoundCloud {item_id} não resolvida.", item=item_id)

        if not download_info.startswith("http"):
             raise InvalidAPIResponseError(f"Informação de download inválida para SoundCloud: '{download_info}'. Esperada URL.", item=item_id)

        # download_info is a URL to a stream manifest (JSON containing the actual stream URL)
        resp_data, _ = await self._request(download_info)

        if not isinstance(resp_data, dict) or "url" not in resp_data:
            raise InvalidAPIResponseError(
                f"Resposta de manifesto de stream SoundCloud inválida de {download_info} para faixa {item_id}.",
                item=item_id
            )

        return SoundcloudDownloadable(
            self.session,
            {"url": resp_data["url"], "type": "mp3"},
        )

    async def resolve_url(self, url: str) -> dict:
        resp_data, _ = await self._api_request("resolve", params={"url": url})

        if not isinstance(resp_data, dict) or "kind" not in resp_data:
            raise InvalidAPIResponseError(f"Resposta de resolve do SoundCloud inválida para URL {url}.", item=url)

        if resp_data["kind"] == "track":
            try:
                resp_data["id"] = self._get_custom_id(resp_data)
            except (SoundcloudAPIError, InvalidAPIResponseError, AssertionError) as e:
                logger.warning(f"Falha ao gerar ID customizado para faixa resolvida {resp_data.get('id')} de {url}: {e}")
                original_id = resp_data.get("id", f"unknown_resolved_track_from_{url}")
                resp_data["id"] = f"{original_id}|{self.NON_STREAMABLE}"
        return resp_data

    async def _get_track(self, item_id: str) -> dict:
        if not item_id.isdigit(): # Basic validation
            raise SoundcloudAPIError(f"ID de faixa SoundCloud inválido fornecido para _get_track: {item_id}", item=item_id)
        resp_data, _ = await self._api_request(f"tracks/{item_id}")
        if not isinstance(resp_data, dict): # Check if response is a dictionary
            raise InvalidAPIResponseError(f"Resposta de faixa SoundCloud inválida para ID {item_id}.", item=item_id)
        return resp_data

    async def _get_playlist(self, playlist_id: str) -> dict:
        if not playlist_id.isdigit(): # Basic validation
            raise SoundcloudAPIError(f"ID de playlist SoundCloud inválido fornecido para _get_playlist: {playlist_id}", item=playlist_id)

        playlist_data, _ = await self._api_request(f"playlists/{playlist_id}")

        if not isinstance(playlist_data, dict) or not isinstance(playlist_data.get("tracks"), list):
            raise InvalidAPIResponseError(f"Resposta de playlist SoundCloud inválida para ID {playlist_id}.", item=playlist_id)

        unresolved_track_ids = [
            track.get("id") for track in playlist_data.get("tracks", [])
            if isinstance(track, dict) and ( # Ensure track is a dict and has an id
                "media" not in track or
                not isinstance(track.get("media"), dict) or # media should be a dict
                "transcodings" not in track.get("media", {}) or # transcodings should be in media
                not isinstance(track.get("media", {}).get("transcodings"), list) or # transcodings should be a list
                # Check if any valid HLS MP3 transcoding exists
                not any(
                    isinstance(tc, dict) and isinstance(tc.get("format"), dict) and
                    tc.get("format", {}).get("protocol") == "hls" and
                    tc.get("format", {}).get("mime_type") == "audio/mpeg" and
                    isinstance(tc.get("url"), str) and tc.get("url", "").startswith("http")
                    for tc in track.get("media", {}).get("transcodings", [])
                )
            ) and track.get("streamable") and track.get("id") is not None # Only if streamable and has ID
        ]
        # Filter out None or non-digit IDs from the list
        unresolved_track_ids = [str(tid) for tid in unresolved_track_ids if tid is not None and str(tid).isdigit()]


        if not unresolved_track_ids:
            logger.debug(f"Todas as faixas na playlist SoundCloud {playlist_id} já estão resolvidas ou não são streamable/válidas.")
            for i, track_in_playlist in enumerate(playlist_data.get("tracks", [])):
                if isinstance(track_in_playlist, dict) and "id" in track_in_playlist:
                    try:
                        playlist_data["tracks"][i]["id"] = self._get_custom_id(track_in_playlist)
                    except (SoundcloudAPIError, InvalidAPIResponseError, AssertionError) as e:
                        logger.warning(f"Falha ao gerar ID customizado para faixa {track_in_playlist.get('id')} na playlist {playlist_id}: {e}")
                        playlist_data["tracks"][i]["id"] = f"{track_in_playlist.get('id')}|{self.NON_STREAMABLE}"
            return playlist_data

        logger.debug(f"Resolvendo {len(unresolved_track_ids)} faixas para playlist SoundCloud {playlist_id}.")

        resolved_tracks_map = {}
        batches = batched(unresolved_track_ids, MAX_BATCH_SIZE)

        track_requests_coroutines = []
        for batch in batches:
            current_batch_ids = [tid for tid in batch if tid is not None] # Already strings
            if not current_batch_ids:
                continue
            track_requests_coroutines.append(
                self._api_request("tracks", params={"ids": ",".join(current_batch_ids)})
            )

        batch_responses = await asyncio.gather(*track_requests_coroutines, return_exceptions=True)

        for resp_item in batch_responses:
            if isinstance(resp_item, Exception):
                logger.error(f"Erro ao buscar lote de faixas para playlist {playlist_id}: {resp_item}", exc_info=True)
                continue

            batch_data, _ = resp_item
            if isinstance(batch_data, list):
                for track_detail in batch_data:
                    if isinstance(track_detail, dict) and "id" in track_detail:
                        resolved_tracks_map[track_detail["id"]] = track_detail # Store by original int/str ID
            else:
                logger.warning(f"Resposta de lote de faixas inesperada para playlist {playlist_id}: {batch_data}")

        final_tracks = []
        for track_stub in playlist_data.get("tracks", []):
            if not isinstance(track_stub, dict) or "id" not in track_stub:
                logger.warning(f"Item de faixa inválido na playlist {playlist_id}: {track_stub}")
                continue

            original_track_id = track_stub["id"] # This ID is an int from SC API
            # Use original_track_id (int) for map lookup, as that's how they were stored
            full_track_data = resolved_tracks_map.get(original_track_id, track_stub)

            try:
                full_track_data["id"] = self._get_custom_id(full_track_data) # This will now be "int_id|url_or_flag"
            except (SoundcloudAPIError, InvalidAPIResponseError, AssertionError, KeyError) as e:
                logger.warning(f"Falha ao gerar ID customizado para faixa {original_track_id} na playlist {playlist_id}: {e}")
                full_track_data["id"] = f"{original_track_id}|{self.NON_STREAMABLE}"
            final_tracks.append(full_track_data)

        playlist_data["tracks"] = final_tracks
        return playlist_data

    @classmethod
    def _get_custom_id(cls, track_data: dict) -> str:
        if not isinstance(track_data, dict):
            # Added item_id for context if available in track_data, though track_data itself is the problem here.
            item_id_for_log = track_data.get("id", "ID desconhecido") if isinstance(track_data, dict) else "Dados inválidos"
            raise InvalidAPIResponseError(f"Dados da faixa inválidos para _get_custom_id: esperado dict, obteve {type(track_data)}", item=item_id_for_log)

        item_id = track_data.get("id")
        if item_id is None:
            raise InvalidAPIResponseError(f"ID da faixa ausente nos dados para _get_custom_id: {track_data.get('permalink_url', 'URL desconhecida')}")

        media_info = track_data.get("media")
        if not isinstance(media_info, dict) or not isinstance(media_info.get("transcodings"), list):
            logger.warning(f"Informação de mídia/transcodings ausente ou inválida para faixa SoundCloud {item_id}. Marcando como não streamable.")
            return f"{item_id}|{cls.NON_STREAMABLE}"

        if not track_data.get("streamable") or track_data.get("policy") == "BLOCK":
            return f"{item_id}|{cls.NON_STREAMABLE}"

        if track_data.get("downloadable") and track_data.get("has_downloads_left"):
            return f"{item_id}|{cls.ORIGINAL_DOWNLOAD}"

        hls_mp3_stream_url = None
        for tc in media_info.get("transcodings", []): # Safe default for transcodings
            if not isinstance(tc, dict): continue
            fmt = tc.get("format", {})
            if isinstance(fmt, dict) and fmt.get("protocol") == "hls" and fmt.get("mime_type") == "audio/mpeg":
                url_candidate = tc.get("url")
                if isinstance(url_candidate, str) and url_candidate.startswith("http"): # Basic URL validation
                    hls_mp3_stream_url = url_candidate
                    break

        if hls_mp3_stream_url:
            return f"{item_id}|{hls_mp3_stream_url}"

        logger.warning(f"Nenhum stream HLS MP3 utilizável encontrado para faixa SoundCloud {item_id}.")
        return f"{item_id}|{cls.NON_STREAMABLE}"

    async def _api_request(self, path: str, params: dict | None = None, headers: dict | None = None) -> tuple[dict, int]:
        url = f"{BASE}/{path}"
        return await self._request(url, params=params, headers=headers)

    async def _request(self, url: str, params: dict | None = None, headers: dict | None = None) -> tuple[dict, int]:
        if not self.config.client_id:
            logger.warning("Client ID do SoundCloud não configurado antes da solicitação. Tentando atualizar tokens...")
            try:
                refreshed_client_id, refreshed_app_version = await self._refresh_tokens()
                self.config.client_id = refreshed_client_id
                self.config.app_version = refreshed_app_version
                # Persist refreshed tokens
                cs_glob = self.global_config.session.soundcloud
                cf_glob = self.global_config.file.soundcloud
                cs_glob.client_id, cf_glob.client_id = refreshed_client_id, refreshed_client_id
                cs_glob.app_version, cf_glob.app_version = refreshed_app_version, refreshed_app_version
                self.global_config.file.set_modified()
            except (NetworkError, SoundcloudAPIError) as e:
                raise ClientError(f"Falha ao obter client_id do SoundCloud necessário para a solicitação: {e}") from e

        request_params = {
            "client_id": self.config.client_id,
            "app_version": self.config.app_version or "None",
            "app_locale": "en",
        }
        if params:
            request_params.update(params)

        current_retry = 0
        while True:
            logger.debug("SoundCloud request: url=%s, params=%s, attempt=%d", url, request_params, current_retry + 1)
            try:
                async with self.rate_limiter:
                    async with self.session.get(url, params=request_params, headers=headers) as http_resp:
                        try:
                            resp_data = await http_resp.json(content_type=None)
                        except (aiohttp.ContentTypeError, JSONDecodeError) as json_err:
                            resp_text = await http_resp.text()
                            logger.warning(
                                f"Resposta não-JSON (ou falha na decodificação) da API SoundCloud para {url} (status {http_resp.status}): {json_err}. Texto: {resp_text[:100]}"
                            )
                            if BASE in url or http_resp.status >= 400 :
                                raise InvalidAPIResponseError(f"Resposta SoundCloud não é JSON válido de {url} (status {http_resp.status}).", item=url) from json_err
                            resp_data = {"message": resp_text[:200], "_raw_content": True}

                        status_code = http_resp.status
                        if status_code == 401:
                             logger.warning(f"SoundCloud API retornou 401 Unauthorized para {url}. Client_id pode precisar de atualização.")
                             if current_retry == 0:
                                 logger.info("Tentando atualizar client_id do SoundCloud devido a erro 401...")
                                 try:
                                     new_client_id, new_app_version = await self._refresh_tokens()
                                     self.config.client_id = new_client_id
                                     self.config.app_version = new_app_version
                                     request_params["client_id"] = new_client_id
                                     request_params["app_version"] = new_app_version
                                     # Persist
                                     cs_glob = self.global_config.session.soundcloud
                                     cf_glob = self.global_config.file.soundcloud
                                     cs_glob.client_id, cf_glob.client_id = new_client_id, new_client_id
                                     cs_glob.app_version, cf_glob.app_version = new_app_version, new_app_version
                                     self.global_config.file.set_modified()
                                     current_retry += 1
                                     continue
                                 except (NetworkError, SoundcloudAPIError) as refresh_e:
                                     logger.error(f"Falha ao atualizar client_id do SoundCloud após 401: {refresh_e}")
                             raise SoundcloudAPIError(f"Não autorizado (401) para {url}. Client_id pode estar desatualizado.", item=url)

                        if status_code == 404:
                            raise ResourceNotFoundError(f"Recurso SoundCloud não encontrado: {url}", item=url)
                        if status_code == 429:
                            delay = (self.initial_retry_delay * (2**current_retry)) + (hashlib.md5(str(request_params).encode()).digest()[0] / 255.0)
                            logger.warning(
                                f"Limite de taxa da API SoundCloud atingido para {url} (status 429). "
                                f"Tentando novamente em {delay:.2f}s... (tentativa {current_retry + 1}/{self.max_retries})"
                            )
                            if current_retry < self.max_retries:
                                await asyncio.sleep(delay)
                                current_retry += 1
                                continue
                            raise APILimitError(
                                f"Limite de taxa da API SoundCloud excedido para {url} após {self.max_retries} tentativas.", item=url
                            )

                        if status_code >= 400 :
                            error_message = "Erro desconhecido da API SoundCloud"
                            if isinstance(resp_data, dict):
                                if "errors" in resp_data and isinstance(resp_data["errors"], list) and resp_data["errors"]:
                                    error_detail = resp_data["errors"][0]
                                    if isinstance(error_detail, dict) and "error_message" in error_detail:
                                         error_message = error_detail["error_message"]
                                elif "message" in resp_data:
                                    error_message = resp_data["message"]
                            raise SoundcloudAPIError(f"Erro da API SoundCloud {status_code} para {url}: {error_message}", item=url)

                        if BASE in url and not isinstance(resp_data, dict):
                             logger.error(f"Resposta da API SoundCloud para {url} não é um dicionário: {type(resp_data)}")
                             raise InvalidAPIResponseError(f"Resposta da API SoundCloud para {url} não é um dicionário.", item=url)

                        return resp_data, status_code

            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError, aiohttp.ClientOSError) as e:
                logger.warning(f"Erro de conexão/rede com API SoundCloud ({url}): {e}. Tentativa {current_retry + 1}/{self.max_retries}")
                if current_retry < self.max_retries:
                    await asyncio.sleep(self.initial_retry_delay * (2**current_retry))
                    current_retry += 1
                    continue
                raise NetworkError(f"Erro de conexão com API SoundCloud ({url}) após {self.max_retries} tentativas: {e}", item=url) from e
            except asyncio.TimeoutError as e:
                logger.warning(f"Timeout ao conectar com API SoundCloud ({url}). Tentativa {current_retry + 1}/{self.max_retries}")
                if current_retry < self.max_retries:
                    await asyncio.sleep(self.initial_retry_delay * (2**current_retry))
                    current_retry += 1
                    continue
                raise NetworkError(f"Timeout ao conectar com API SoundCloud ({url}) após {self.max_retries} tentativas.", item=url) from e
            except aiohttp.ClientError as e:
                logger.warning(f"Erro de cliente HTTP com API SoundCloud ({url}): {e}. Tentativa {current_retry + 1}/{self.max_retries}")
                if current_retry < self.max_retries and not isinstance(e, aiohttp.InvalidURL):
                    await asyncio.sleep(self.initial_retry_delay * (2**current_retry))
                    current_retry += 1
                    continue
                raise NetworkError(f"Erro de cliente HTTP com API SoundCloud ({url}): {e}", item=url) from e

    async def _request_body(self, url: str, params: dict | None = None, headers: dict | None = None) -> tuple[bytes, int]:
        if not self.config.client_id:
             raise ClientError("Client ID do SoundCloud não configurado para _request_body.")

        request_params = {
            "client_id": self.config.client_id,
            "app_version": self.config.app_version or "None",
            "app_locale": "en",
        }
        if params:
            request_params.update(params)

        current_retry = 0
        while True:
            logger.debug("SoundCloud _request_body: url=%s, params=%s, attempt=%d", url, request_params, current_retry + 1)
            try:
                async with self.rate_limiter:
                    async with self.session.get(url, params=request_params, headers=headers) as http_resp:
                        status_code = http_resp.status
                        if status_code == 429:
                            delay = (self.initial_retry_delay * (2**current_retry)) + (hashlib.md5(str(request_params).encode()).digest()[0] / 255.0)
                            logger.warning(f"Limite de taxa (429) para _request_body SoundCloud {url}. Tentando em {delay:.2f}s...")
                            if current_retry < self.max_retries:
                                await asyncio.sleep(delay)
                                current_retry += 1
                                continue
                            raise APILimitError(f"Limite de taxa excedido para _request_body {url} após {self.max_retries} tentativas.", item=url)

                        body_bytes = await http_resp.content.read()
                        if status_code != 200: # Includes 401 for _announce_success
                             logger.debug(f"SoundCloud _request_body para {url} retornou status {status_code}.")
                        return body_bytes, status_code
            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError, aiohttp.ClientOSError) as e:
                logger.warning(f"Erro de conexão/rede em _request_body SoundCloud ({url}): {e}. Tentativa {current_retry + 1}/{self.max_retries}")
                if current_retry < self.max_retries:
                    await asyncio.sleep(self.initial_retry_delay * (2**current_retry))
                    current_retry += 1
                    continue
                raise NetworkError(f"Erro de conexão em _request_body SoundCloud ({url}) após {self.max_retries} tentativas: {e}", item=url) from e
            except asyncio.TimeoutError as e:
                logger.warning(f"Timeout em _request_body SoundCloud ({url}). Tentativa {current_retry + 1}/{self.max_retries}")
                if current_retry < self.max_retries:
                    await asyncio.sleep(self.initial_retry_delay * (2**current_retry))
                    current_retry += 1
                    continue
                raise NetworkError(f"Timeout em _request_body SoundCloud ({url}) após {self.max_retries} tentativas.", item=url) from e
            except aiohttp.ClientError as e: # Catch other client errors
                raise NetworkError(f"Erro de cliente HTTP em _request_body SoundCloud ({url}): {e}", item=url) from e

    async def _announce_success(self) -> bool:
        url = f"{BASE}/announcements"
        try:
            _, status = await self._request_body(url)
            if status == 401:
                logger.warning("Falha no _announce_success do SoundCloud (401): tokens provavelmente inválidos.")
                return False
            return status == 200
        except (NetworkError, APILimitError) as e:
            logger.warning(f"Erro de rede ou limite de taxa ao verificar anúncios do SoundCloud: {e}")
            return False
        except Exception as e:
             logger.error(f"Erro inesperado em _announce_success: {e}", exc_info=True)
             return False

    async def _refresh_tokens(self) -> tuple[str, str]:
        """Return a valid client_id, app_version pair by scraping SoundCloud website."""
        try:
            logger.debug(f"Tentando buscar página principal do SoundCloud de {STOCK_URL}")
            async with self.session.get(STOCK_URL) as resp:
                if resp.status == 429:
                    raise APILimitError(f"Limite de taxa ao buscar {STOCK_URL} para atualizar tokens.")
                resp.raise_for_status()
                page_text = await resp.text(encoding="utf-8")
        except aiohttp.ClientError as e:
            raise NetworkError(f"Erro de rede ao buscar página principal do SoundCloud ({STOCK_URL}): {e}") from e
        except Exception as e:
            raise SoundcloudAPIError(f"Erro inesperado ao buscar página principal do SoundCloud: {e}") from e

        script_src_matches = list(re.finditer(r"<script\s+crossorigin\s+src=\"([^\"]+)\"", page_text))
        if not script_src_matches:
            raise SoundcloudAPIError(f"Não foi possível encontrar URLs de script candidatas para client_id em {STOCK_URL}")

        client_id_script_url = script_src_matches[-1].group(1)
        logger.debug(f"URL do script candidata para client_id: {client_id_script_url}")

        app_version_match = re.search(r'<script>window\.__sc_version="(\d+)"</script>', page_text)
        if app_version_match is None:
            raise SoundcloudAPIError(f"Não foi possível encontrar app_version na página principal do SoundCloud ({STOCK_URL})")
        app_version = app_version_match.group(1)
        logger.debug(f"App version encontrado: {app_version}")

        try:
            logger.debug(f"Tentando buscar script do client_id de {client_id_script_url}")
            async with self.session.get(client_id_script_url) as resp:
                if resp.status == 429:
                    raise APILimitError(f"Limite de taxa ao buscar script do client_id de {client_id_script_url}.")
                resp.raise_for_status()
                script_content = await resp.text(encoding="utf-8")
        except aiohttp.ClientError as e:
            raise NetworkError(f"Erro de rede ao buscar script do client_id ({client_id_script_url}): {e}") from e
        except Exception as e:
             raise SoundcloudAPIError(f"Erro inesperado ao buscar script do client_id: {e}") from e

        client_id_match = re.search(r'client_id\s*:\s*"([a-zA-Z0-9_]{32})"', script_content)
        if client_id_match is None:
             client_id_match = re.search(r'client_id\s*:\s*"([a-zA-Z0-9_]+)"', script_content)
             if client_id_match is None:
                raise SoundcloudAPIError(f"Não foi possível encontrar client_id no conteúdo do script de {client_id_script_url}")
        client_id = client_id_match.group(1)

        logger.info(f"Tokens SoundCloud atualizados: client_id={client_id}, app_version={app_version}")
        return client_id, app_version
>>>>>>> REPLACE
