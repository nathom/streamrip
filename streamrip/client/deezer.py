import asyncio
import binascii
import hashlib
import logging

import deezer
from Cryptodome.Cipher import AES

from ..config import Config
from ..exceptions import (
    AuthenticationError,
    DeezerAPIError,
    InvalidAPIResponseError,
    MissingCredentialsError,
    NetworkError, # Assuming deezer.py might raise something mappable to this
    NonStreamableError,
    ResourceNotFoundError,
)
from .client import Client
from .downloadable import DeezerDownloadable

logger = logging.getLogger("streamrip")
logging.captureWarnings(True)


class DeezerClient(Client):
    """Client to handle deezer API. Does not do rate limiting.

    Attributes:
        global_config: Entire config object
        client: client from deezer py used for API requests
        logged_in: True if logged in
        config: deezer local config
        session: aiohttp.ClientSession, used only for track downloads not API requests

    """

    source = "deezer"
    max_quality = 2

    def __init__(self, config: Config):
        self.global_config = config
        self.client = deezer.Deezer()
        self.logged_in = False
        self.config = config.session.deezer

    async def login(self):
        # Used for track downloads
        try:
            self.session = await self.get_session(
                verify_ssl=self.global_config.session.downloads.verify_ssl
            )
        except Exception as e:
            raise NetworkError(f"Falha ao inicializar a sessão HTTP para Deezer: {e}") from e

        arl = self.config.arl
        if not arl:
            raise MissingCredentialsError("ARL do Deezer não configurado.")

        try:
            # Assuming login_via_arl is synchronous and might raise its own errors
            # or return False on failure.
            # deezer.DeezerError or deezer.LoginError might be relevant if they exist.
            success = await asyncio.to_thread(self.client.login_via_arl, arl)
            if not success:
                # This could be due to invalid ARL or other issues.
                raise AuthenticationError("Falha no login do Deezer. Verifique o ARL.")
        except deezer.errors.DeezerError as e: # Catch specific Deezer lib errors if possible
            # Example: Map specific Deezer errors to our custom exceptions
            # This part is speculative without knowing exact exceptions from deezer-py for login
            if "invalid arl" in str(e).lower(): # Example check
                 raise AuthenticationError(f"ARL do Deezer inválido: {e}") from e
            raise DeezerAPIError(f"Erro da API do Deezer durante o login: {e}") from e
        except Exception as e: # Catch-all for other unexpected errors during login
            raise AuthenticationError(f"Erro inesperado durante o login no Deezer: {e}") from e

        self.logged_in = True
        logger.info("Login no Deezer bem-sucedido.")

    async def _handle_deezer_api_call(self, api_func, *args, item_id_for_log=None):
        """Wraps deezer-py API calls for error handling."""
        try:
            # Convert synchronous deezer-py calls to async
            result = await asyncio.to_thread(api_func, *args)
            if result is None: # Some API calls might return None on "not found"
                raise ResourceNotFoundError(f"Recurso não encontrado no Deezer: {item_id_for_log or args}", item=item_id_for_log)
            # Deezer API often wraps results in a dictionary, e.g. {'data': [...], 'total': ...}
            # or directly returns the dict for single items.
            # We need to be careful if 'error' key indicates an API-level error despite 200 OK.
            if isinstance(result, dict) and result.get("error"):
                error_details = result["error"]
                error_type = error_details.get("type", "UnknownDeezerError")
                error_message = error_details.get("message", "Erro desconhecido da API Deezer.")
                if error_details.get("code") == 800: # Example: Data not found
                    raise ResourceNotFoundError(f"Recurso não encontrado no Deezer: {error_message}", item=item_id_for_log)
                raise DeezerAPIError(f"{error_type}: {error_message}", item=item_id_for_log)
            return result
        except deezer.errors.DeezerError as e: # Base error for deezer-py
            # Try to map specific deezer.errors if they exist, e.g., NotFoundError, RateLimitError
            # This is speculative as deezer-py's specific error types aren't fully known here.
            # For now, map based on typical API error patterns.
            err_str = str(e).lower()
            if "not found" in err_str or hasattr(e, 'code') and getattr(e, 'code') == 800:
                raise ResourceNotFoundError(f"Recurso não encontrado no Deezer: {e}", item=item_id_for_log) from e
            # Add more mappings here if other deezer.py errors are known (e.g., for rate limits)
            raise DeezerAPIError(f"Erro da API do Deezer: {e}", item=item_id_for_log) from e
        except Exception as e: # Catch-all for unexpected errors from the library or threading
            # Could be a NetworkError if the sync library call fails due to network,
            # but it's hard to distinguish without deeper library knowledge.
            logger.error(f"Erro inesperado durante chamada à API do Deezer para {item_id_for_log or api_func.__name__}: {e}", exc_info=True)
            raise DeezerAPIError(f"Erro inesperado ao interagir com a API do Deezer: {e}", item=item_id_for_log) from e


    async def get_metadata(self, item_id: str, media_type: str) -> dict:
        if media_type == "track":
            return await self.get_track(item_id)
        elif media_type == "album":
            return await self.get_album(item_id)
        elif media_type == "playlist":
            return await self.get_playlist(item_id)
        elif media_type == "artist":
            return await self.get_artist(item_id)
        else:
            raise DeezerAPIError(f"Tipo de mídia '{media_type}' não disponível no Deezer.")


    async def get_track(self, item_id: str) -> dict:
        item = await self._handle_deezer_api_call(self.client.api.get_track, item_id, item_id_for_log=item_id)

        if not isinstance(item, dict) or "album" not in item or "id" not in item["album"]:
            raise InvalidAPIResponseError(f"Resposta de faixa inválida do Deezer para ID {item_id} (álbum ausente).", item=item_id)

        album_id = item["album"]["id"]
        try:
            # Fetch album metadata and its tracks list concurrently
            album_metadata_task = self._handle_deezer_api_call(self.client.api.get_album, album_id, item_id_for_log=f"album {album_id} for track {item_id}")
            album_tracks_data_task = self._handle_deezer_api_call(self.client.api.get_album_tracks, album_id, item_id_for_log=f"tracks for album {album_id}")
            album_metadata, album_tracks_response = await asyncio.gather(album_metadata_task, album_tracks_data_task)

            if not isinstance(album_metadata, dict):
                 raise InvalidAPIResponseError(f"Metadados do álbum inválidos para ID {album_id}.", item=album_id)
            if not isinstance(album_tracks_response, dict) or "data" not in album_tracks_response:
                 raise InvalidAPIResponseError(f"Resposta de faixas do álbum inválida para ID {album_id}.", item=album_id)

            album_metadata["tracks"] = album_tracks_response["data"]
            album_metadata["track_total"] = len(album_tracks_response["data"]) # Or use album_metadata.get('nb_tracks')
            item["album"] = album_metadata # Replace partial album data with full album metadata
        except (DeezerAPIError, ResourceNotFoundError, InvalidAPIResponseError) as e:
            logger.warning(f"Não foi possível buscar detalhes completos do álbum para a faixa {item_id} (álbum ID: {album_id}): {e}")
            # Item already contains partial album info, so we can proceed with that if full fetch fails.

        return item

    async def get_album(self, item_id: str) -> dict:
        album_metadata_task = self._handle_deezer_api_call(self.client.api.get_album, item_id, item_id_for_log=f"album {item_id}")
        album_tracks_data_task = self._handle_deezer_api_call(self.client.api.get_album_tracks, item_id, item_id_for_log=f"tracks for album {item_id}")
        album_metadata, album_tracks_response = await asyncio.gather(album_metadata_task, album_tracks_data_task)

        if not isinstance(album_metadata, dict):
            raise InvalidAPIResponseError(f"Metadados do álbum inválidos para ID {item_id}.", item=item_id)
        if not isinstance(album_tracks_response, dict) or "data" not in album_tracks_response:
            raise InvalidAPIResponseError(f"Resposta de faixas do álbum inválida para ID {item_id}.", item=item_id)

        album_metadata["tracks"] = album_tracks_response["data"]
        # nb_tracks from get_album is usually more reliable for total in album
        album_metadata["track_total"] = album_metadata.get("nb_tracks", len(album_tracks_response["data"]))
        return album_metadata

    async def get_playlist(self, item_id: str) -> dict:
        pl_metadata_task = self._handle_deezer_api_call(self.client.api.get_playlist, item_id, item_id_for_log=f"playlist {item_id}")
        pl_tracks_data_task = self._handle_deezer_api_call(self.client.api.get_playlist_tracks, item_id, item_id_for_log=f"tracks for playlist {item_id}")
        pl_metadata, pl_tracks_response = await asyncio.gather(pl_metadata_task, pl_tracks_data_task)

        if not isinstance(pl_metadata, dict):
            raise InvalidAPIResponseError(f"Metadados da playlist inválidos para ID {item_id}.", item=item_id)
        if not isinstance(pl_tracks_response, dict) or "data" not in pl_tracks_response:
            raise InvalidAPIResponseError(f"Resposta de faixas da playlist inválida para ID {item_id}.", item=item_id)

        pl_metadata["tracks"] = pl_tracks_response["data"]
        pl_metadata["track_total"] = pl_metadata.get("nb_tracks", len(pl_tracks_response["data"]))
        return pl_metadata

    async def get_artist(self, item_id: str) -> dict:
        artist_task = self._handle_deezer_api_call(self.client.api.get_artist, item_id, item_id_for_log=f"artist {item_id}")
        albums_task = self._handle_deezer_api_call(self.client.api.get_artist_albums, item_id, item_id_for_log=f"albums for artist {item_id}")
        artist_data, albums_response = await asyncio.gather(artist_task, albums_task)

        if not isinstance(artist_data, dict):
            raise InvalidAPIResponseError(f"Dados do artista inválidos para ID {item_id}.", item=item_id)
        if not isinstance(albums_response, dict) or "data" not in albums_response:
            raise InvalidAPIResponseError(f"Resposta de álbuns do artista inválida para ID {item_id}.", item=item_id)

        artist_data["albums"] = albums_response["data"]
        return artist_data

    async def search(self, media_type: str, query: str, limit: int = 200) -> list[dict]:
        search_func_name = ""
        if media_type == "featured":
            search_func_name = f"get_editorial_{query}" if query else "get_editorial_releases"
        else:
            search_func_name = f"search_{media_type}"

        try:
            search_function_to_call = getattr(self.client.api, search_func_name)
        except AttributeError:
            valid_editorial_queries = "[releases, selection, charts, new_releases, top_playlists, etc.]" # Add more if known
            error_msg = (f"Seleção editorial inválida '{query}'. Queries válidas: {valid_editorial_queries}"
                         if media_type == "featured"
                         else f"Tipo de mídia inválido para pesquisa no Deezer: {media_type}")
            raise DeezerAPIError(error_msg, item=query if media_type == "featured" else media_type)

        # The deezer-py search functions might not consistently support a 'limit' param in their signature,
        # or it might be named differently (e.g. 'nb' for number).
        # For simplicity, we'll try passing 'limit' and let deezer-py handle it or ignore it.
        # A more robust solution would inspect signature or use specific kwargs per function.
        try:
            # Assuming search functions are synchronous and might take query and limit
            response = await self._handle_deezer_api_call(search_function_to_call, query, limit=limit, item_id_for_log=f"search {media_type} '{query}'")
        except TypeError: # If limit kwarg is not accepted by the specific search_function
             response = await self._handle_deezer_api_call(search_function_to_call, query, item_id_for_log=f"search {media_type} '{query}' (no limit)")


        if isinstance(response, dict) and response.get("data") is not None and response.get("total", 0) > 0:
            # Search results are typically under 'data'. The whole response dict is one "page".
            return [response]
        elif isinstance(response, list): # Some editorial calls might return a list directly
             if response: # If list is not empty
                 return [{"data": response, "total": len(response)}] # Wrap in standard page format

        logger.debug(f"Nenhum resultado encontrado para pesquisa Deezer: tipo={media_type}, query='{query}'")
        return []


    async def get_downloadable(
        self,
        item_id: str,
        quality: int = 2,
        is_retry: bool = False,
    ) -> DeezerDownloadable:
        if item_id is None:
            raise NonStreamableError(
                "No item id provided. This can happen when searching for fallback songs.",
            )
        # TODO: optimize such that all of the ids are requested at once
        dl_info: dict = {"quality": quality, "id": item_id}

        try:
            # Assuming gw.get_track is synchronous
            track_info = await asyncio.to_thread(self.client.gw.get_track, item_id)
        except Exception as e: # Broad exception for initial track info fetch
            # This could be due to various reasons, including track not found by ID.
            logger.error(f"Erro ao buscar informações da faixa Deezer (gw) para ID {item_id}: {e}", exc_info=True)
            # Try to map if it's a known deezer-py error for not found
            if "not found" in str(e).lower(): # Heuristic
                raise ResourceNotFoundError(f"Faixa Deezer ID {item_id} não encontrada via gateway.", item=item_id) from e
            raise DeezerAPIError(f"Falha ao obter informações da faixa Deezer (gw) para ID {item_id}: {e}", item=item_id) from e

        if not isinstance(track_info, dict) or "TRACK_TOKEN" not in track_info:
            # If track_info is None or missing essential data (like TRACK_TOKEN)
            # Try fallback if available and not already a retry
            fallback_id = track_info.get("FALLBACK", {}).get("SNG_ID") if isinstance(track_info, dict) else None
            if fallback_id and not is_retry:
                logger.warning(f"Informações da faixa Deezer para ID {item_id} inválidas ou token ausente. Tentando fallback ID {fallback_id}.")
                return await self.get_downloadable(fallback_id, quality, is_retry=True)
            raise InvalidAPIResponseError(f"Resposta de informações da faixa Deezer (gw) inválida ou token ausente para ID {item_id}.", item=item_id)

        fallback_id = track_info.get("FALLBACK", {}).get("SNG_ID")

        quality_map = [
            (9, "MP3_128"),  # quality 0
            (3, "MP3_320"),  # quality 1
            (1, "FLAC"),     # quality 2
        ]

        if not (0 <= quality < len(quality_map)):
            raise ValueError(f"Qualidade Deezer inválida: {quality}. Deve estar entre 0 e {len(quality_map) - 1}.")

        _, format_str = quality_map[quality]

        dl_info["quality_to_size"] = [
            int(track_info.get(f"FILESIZE_{fmt}", 0)) for _, fmt in quality_map
        ]

        track_token = track_info["TRACK_TOKEN"]
        stream_url = None
        try:
            logger.debug(f"Buscando URL de stream Deezer com token {track_token} para formato {format_str}")
            # Assuming get_track_url is synchronous
            stream_url = await asyncio.to_thread(self.client.get_track_url, track_token, format_str)
        except deezer.errors.WrongLicense as e:
            msg = ("Qualidade solicitada não disponível com sua assinatura Deezer. "
                   "Deezer HiFi é necessário para qualidade FLAC (2). Máximo permitido pode ser 1 (MP3 320kbps).")
            raise NonStreamableError(msg, item=item_id) from e
        except deezer.errors.WrongGeolocation as e:
            if not is_retry and fallback_id:
                logger.warning(f"Erro de geolocalização para faixa Deezer {item_id}. Tentando fallback ID {fallback_id}.")
                return await self.get_downloadable(fallback_id, quality, is_retry=True)
            msg = "Faixa Deezer não disponível. Isso pode ser devido ao seu país/localização."
            raise NonStreamableError(msg, item=item_id) from e
        except deezer.errors.DeezerError as e: # Catch other specific Deezer errors
            raise DeezerAPIError(f"Erro da API Deezer ao obter URL de stream: {e}", item=item_id) from e
        except Exception as e: # Catch-all for unexpected errors from get_track_url
            raise DeezerAPIError(f"Erro inesperado ao obter URL de stream Deezer: {e}", item=item_id) from e


        if stream_url is None: # If get_track_url returns None (e.g. for encrypted tracks)
            md5_origin = track_info.get("MD5_ORIGIN")
            media_version = track_info.get("MEDIA_VERSION")
            if not md5_origin or not media_version:
                raise InvalidAPIResponseError(
                    "MD5_ORIGIN ou MEDIA_VERSION ausente para URL de arquivo criptografado Deezer.", item=item_id
                )
            stream_url = self._get_encrypted_file_url(item_id, md5_origin, media_version)

        dl_info["url"] = stream_url
        logger.debug(f"Informações da faixa Deezer (dl_info): {dl_info}")
        return DeezerDownloadable(self.session, dl_info)


    def _get_encrypted_file_url(
        self,
        meta_id: str,
        track_hash: str,
        media_version: str,
    ):
        logger.debug("Unable to fetch URL. Trying encryption method.")
        format_number = 1

        url_bytes = b"\xa4".join(
            (
                track_hash.encode(),
                str(format_number).encode(),
                str(meta_id).encode(),
                str(media_version).encode(),
            ),
        )
        url_hash = hashlib.md5(url_bytes).hexdigest()
        info_bytes = bytearray(url_hash.encode())
        info_bytes.extend(b"\xa4")
        info_bytes.extend(url_bytes)
        info_bytes.extend(b"\xa4")
        # Pad the bytes so that len(info_bytes) % 16 == 0
        padding_len = 16 - (len(info_bytes) % 16)
        info_bytes.extend(b"." * padding_len)

        path = binascii.hexlify(
            AES.new(b"jo6aey6haid2Teih", AES.MODE_ECB).encrypt(info_bytes),
        ).decode("utf-8")
        url = f"https://e-cdns-proxy-{track_hash[0]}.dzcdn.net/mobile/1/{path}"
        logger.debug("Encrypted file path %s", url)
        return url
