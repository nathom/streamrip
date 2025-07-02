import asyncio
import base64
import hashlib
import logging
import re
import time
from collections import OrderedDict
from typing import List, Optional

import aiohttp

from ..config import Config
from ..exceptions import (
    APILimitError,
    AuthenticationError,
    ClientError,
    IneligibleError,
    InvalidAPIResponseError,
    InvalidAppIdError,
    InvalidAppSecretError,
    MissingCredentialsError,
    NonStreamableError,
    QobuzAPIError,
    ResourceNotFoundError,
    NetworkError,
)
from .client import Client
from .downloadable import BasicDownloadable, Downloadable

logger = logging.getLogger("streamrip")

QOBUZ_BASE_URL = "https://www.qobuz.com/api.json/0.2"

QOBUZ_FEATURED_KEYS = {
    "most-streamed",
    "recent-releases",
    "best-sellers",
    "press-awards",
    "ideal-discography",
    "editor-picks",
    "most-featured",
    "qobuzissims",
    "new-releases",
    "new-releases-full",
    "harmonia-mundi",
    "universal-classic",
    "universal-jazz",
    "universal-jeunesse",
    "universal-chanson",
}


class QobuzSpoofer:
    """Spoofs the information required to stream tracks from Qobuz."""

    def __init__(self, verify_ssl: bool = True):
        """Create a Spoofer."""
        self.seed_timezone_regex = (
            r'[a-z]\.initialSeed\("(?P<seed>[\w=]+)",window\.ut'
            r"imezone\.(?P<timezone>[a-z]+)\)"
        )
        # note: {timezones} should be replaced with every capitalized timezone joined by a |
        self.info_extras_regex = (
            r'name:"\w+/(?P<timezone>{timezones})",info:"'
            r'(?P<info>[\w=]+)",extras:"(?P<extras>[\w=]+)"'
        )
        self.app_id_regex = (
            r'production:{api:{appId:"(?P<app_id>\d{9})",appSecret:"(\w{32})'
        )
        self.session = None
        self.verify_ssl = verify_ssl

    async def get_app_id_and_secrets(self) -> tuple[str, list[str]]:
        assert self.session is not None, "Session not initialized in QobuzSpoofer"
        try:
            async with self.session.get("https://play.qobuz.com/login") as req:
                req.raise_for_status() # Check for HTTP errors
                login_page = await req.text()
        except aiohttp.ClientError as e:
            raise NetworkError(f"Erro de rede ao buscar a página de login do Qobuz: {e}") from e

        bundle_url_match = re.search(
            r'<script src="(/resources/\d+\.\d+\.\d+-[a-z]\d{3}/bundle\.js)"></script>',
            login_page,
        )
        if bundle_url_match is None:
            raise QobuzAPIError("Não foi possível encontrar a URL do bundle na página de login do Qobuz.")
        bundle_url = bundle_url_match.group(1)

        try:
            async with self.session.get("https://play.qobuz.com" + bundle_url) as req:
                req.raise_for_status()
                self.bundle = await req.text()
        except aiohttp.ClientError as e:
            raise NetworkError(f"Erro de rede ao buscar o bundle.js do Qobuz: {e}") from e

        match = re.search(self.app_id_regex, self.bundle)
        if match is None:
            raise QobuzAPIError("Não foi possível encontrar o app_id no bundle.js do Qobuz.")

        app_id = str(match.group("app_id"))

        # get secrets
        seed_matches = re.finditer(self.seed_timezone_regex, self.bundle)
        secrets = OrderedDict()
        for match in seed_matches:
            seed, timezone = match.group("seed", "timezone")
            secrets[timezone] = [seed]

        """
        The code that follows switches around the first and second timezone.
        Qobuz uses two ternary (a shortened if statement) conditions that
        should always return false. The way Javascript's ternary syntax
        works, the second option listed is what runs if the condition returns
        false. Because of this, we must prioritize the *second* seed/timezone
        pair captured, not the first.
        """

        keypairs = list(secrets.items())
        secrets.move_to_end(keypairs[1][0], last=False)

        info_extras_regex = self.info_extras_regex.format(
            timezones="|".join(timezone.capitalize() for timezone in secrets),
        )
        info_extras_matches = re.finditer(info_extras_regex, self.bundle)
        for match in info_extras_matches:
            timezone, info, extras = match.group("timezone", "info", "extras")
            secrets[timezone.lower()] += [info, extras]

        for secret_pair in secrets:
            secrets[secret_pair] = base64.standard_b64decode(
                "".join(secrets[secret_pair])[:-44],
            ).decode("utf-8")

        vals: List[str] = list(secrets.values())
        if "" in vals:
            vals.remove("")

        secrets_list = vals

        return app_id, secrets_list

    async def __aenter__(self):
        from ..utils.ssl_utils import get_aiohttp_connector_kwargs

        # For the spoofer, always use SSL verification
        connector_kwargs = get_aiohttp_connector_kwargs(verify_ssl=True)
        connector = aiohttp.TCPConnector(**connector_kwargs)

        self.session = aiohttp.ClientSession(connector=connector)
        return self

    async def __aexit__(self, *_):
        if self.session is not None:
            await self.session.close()
        self.session = None


class QobuzClient(Client):
    source = "qobuz"
    max_quality = 4

    def __init__(self, config: Config):
        self.logged_in = False
        self.config = config
        self.rate_limiter = self.get_rate_limiter(
            config.session.downloads.requests_per_minute,
        )
        self.secret: Optional[str] = None
        self.max_retries = 3 # Max retries for network/API limit errors
        self.initial_retry_delay = 1.0 # Initial delay in seconds for retries

    async def _fetch_app_id_and_secrets_if_needed(self, force_refetch: bool = False):
        c = self.config.session.qobuz
        f = self.config.file
        should_fetch = force_refetch or not c.app_id or not c.secrets

        if should_fetch:
            action = "Buscando novamente" if force_refetch else "Buscando"
            logger.info(f"{action} App ID/segredos do Qobuz...")
            try:
                fetched_app_id, fetched_secrets = await self._get_app_id_and_secrets()
                c.app_id = fetched_app_id
                c.secrets = fetched_secrets
                f.qobuz.app_id = fetched_app_id # Save to persistent config
                f.qobuz.secrets = fetched_secrets # Save to persistent config
                f.set_modified()
                logger.info("App ID/segredos do Qobuz obtidos e salvos com sucesso.")
            except (NetworkError, QobuzAPIError) as e:
                raise QobuzAPIError(f"Falha ao obter app_id/segredos do Qobuz: {e}") from e

    async def login(self, attempt_refetch_on_invalid_app_id: bool = True):
        try:
            self.session = await self.get_session(
                verify_ssl=self.config.session.downloads.verify_ssl
            )
        except Exception as e: # Broad exception for session creation issues
            raise ClientError(f"Falha ao inicializar a sessão HTTP: {e}") from e

        c = self.config.session.qobuz
        if not c.email_or_userid or not c.password_or_token:
            raise MissingCredentialsError("E-mail/usuário ou senha/token do Qobuz não configurado.")

        if self.logged_in:
            logger.warning("Tentativa de login quando já estava logado no Qobuz.")
            return

        await self._fetch_app_id_and_secrets_if_needed()

        self.session.headers.update({"X-App-Id": str(c.app_id)})

        if c.use_auth_token:
            params = {
                "user_id": c.email_or_userid,
                "user_auth_token": c.password_or_token,
                "app_id": str(c.app_id),
            }
        else:
            params = {
                "email": c.email_or_userid,
                "password": c.password_or_token,
                "app_id": str(c.app_id),
            }

        logger.debug("Request params %s", params)

        try:
            status, resp_data = await self._api_request("user/login", params)
            logger.debug("Login resp: %s", resp_data)

            if status == 401:
                raise InvalidCredentialsError(f"Credenciais inválidas do Qobuz. Verifique e-mail/senha ou token.")

            if status == 400:
                error_message = resp_data.get("message", "app_id inválido ou solicitação malformada.")
                # Check if it's an app_id issue and if we can refetch
                if "app_id" in error_message.lower() and attempt_refetch_on_invalid_app_id:
                    logger.warning(f"App ID do Qobuz parece inválido ('{error_message}'). Tentando buscar novamente...")
                    await self._fetch_app_id_and_secrets_if_needed(force_refetch=True)
                    # After refetching, update headers and try login again, but only once.
                    self.session.headers.update({"X-App-Id": str(c.app_id)})
                    return await self.login(attempt_refetch_on_invalid_app_id=False)
                raise InvalidAppIdError(error_message)

            if status != 200:
                error_message = resp_data.get("message", f"Erro desconhecido durante o login no Qobuz (status: {status}).")
                raise QobuzAPIError(error_message)

        except InvalidAppIdError as e: # Catch InvalidAppIdError specifically for refetch logic
            if attempt_refetch_on_invalid_app_id:
                logger.warning(f"Falha no login do Qobuz devido a app_id inválido: {e}. Tentando buscar novamente...")
                await self._fetch_app_id_and_secrets_if_needed(force_refetch=True)
                self.session.headers.update({"X-App-Id": str(c.app_id)})
                return await self.login(attempt_refetch_on_invalid_app_id=False)
            raise # Re-raise if we shouldn't refetch or refetch failed

        logger.debug("Logged in to Qobuz")

        user_info = resp_data.get("user")
        if not isinstance(user_info, dict):
            raise InvalidAPIResponseError("Campo 'user' ausente ou inválido na resposta de login do Qobuz.")

        credential_info = user_info.get("credential")
        if not isinstance(credential_info, dict):
            raise InvalidAPIResponseError("Campo 'user.credential' ausente ou inválido na resposta de login do Qobuz.")

        # Qobuz returns an empty list for 'parameters' for free/ineligible accounts.
        # Checking for 'None' might be too strict if API changes to omit for free accounts.
        # The original check was `if not resp["user"]["credential"]["parameters"]:`
        # Let's assume an empty list means ineligible, but presence of key is important.
        if "parameters" not in credential_info:
             raise InvalidAPIResponseError("Campo 'user.credential.parameters' ausente na resposta de login do Qobuz.")
        if not credential_info["parameters"]: # Empty list implies ineligible
            raise IneligibleError("Conta Qobuz não elegível para streaming/download (parâmetros de credencial vazios).")

        uat = user_info.get("user_auth_token")
        if not uat:
            raise InvalidAPIResponseError("Token de autenticação do usuário não encontrado na resposta de login do Qobuz.")

        self.session.headers.update({"X-User-Auth-Token": uat})
        self.secret = await self._get_valid_secret(c.secrets)
        self.logged_in = True

    async def get_metadata(self, item: str, media_type: str):
        if media_type == "label":
            return await self.get_label(item)

        c = self.config.session.qobuz
        params = {
            "app_id": str(c.app_id),
            f"{media_type}_id": item,
            # Do these matter?
            "limit": 500,
            "offset": 0,
        }

        extras = {
            "artist": "albums",
            "playlist": "tracks",
            "label": "albums",
        }

        if media_type in extras:
            params.update({"extra": extras[media_type]})

        logger.debug("request params: %s", params)

        epoint = f"{media_type}/get"

        status, resp_data = await self._api_request(epoint, params)

        if status == 404:
            raise ResourceNotFoundError(
                f"Metadados para {media_type} ID {item} não encontrados no Qobuz.", item=item
            )
        if status != 200:
            message = resp_data.get("message", f"Erro desconhecido ao buscar metadados (status: {status}) para {media_type} ID {item}.")
            raise QobuzAPIError(message, item=item)

        # Example of safer access, assuming resp_data is the dict
        if not isinstance(resp_data, dict):
            raise InvalidAPIResponseError(f"Resposta de metadados inesperada (não é um dicionário) para {media_type} ID {item}.", item=item)
        # Further checks can be added here if specific fields are critical for the caller

        return resp_data

    async def get_label(self, label_id: str) -> dict:
        c = self.config.session.qobuz
        page_limit = 500
        params = {
            "app_id": str(c.app_id),
            "label_id": label_id,
            "limit": page_limit,
            "offset": 0,
            "extra": "albums",
        }
        epoint = "label/get"
        status, label_resp_data = await self._api_request(epoint, params)

        if status == 404:
            raise ResourceNotFoundError(f"Selo com ID {label_id} não encontrado no Qobuz.", item=label_id)
        if status != 200:
            message = label_resp_data.get("message", f"Erro desconhecido ao buscar selo {label_id} (status: {status}).")
            raise QobuzAPIError(message, item=label_id)

        if not isinstance(label_resp_data, dict):
            raise InvalidAPIResponseError(f"Resposta de selo inesperada (não é um dicionário) para ID {label_id}.", item=label_id)

        albums_count = label_resp_data.get("albums_count", 0)

        if albums_count <= page_limit:
            return label_resp_data

        # Ensure 'albums' and 'items' keys exist and are dict/list respectively
        albums_section = label_resp_data.get("albums")
        if not isinstance(albums_section, dict):
            label_resp_data["albums"] = {"items": []} # Initialize if 'albums' is missing or not a dict
            albums_section = label_resp_data["albums"]

        if not isinstance(albums_section.get("items"), list):
            albums_section["items"] = [] # Initialize if 'items' is missing or not a list


        requests = [
            self._api_request(
                epoint,
                {
                    "app_id": str(c.app_id),
                    "label_id": label_id,
                    "limit": page_limit,
                    "offset": offset,
                    "extra": "albums",
                },
            )
            for offset in range(page_limit, albums_count, page_limit)
        ]

        results = await asyncio.gather(*requests, return_exceptions=True)

        current_items = label_resp_data["albums"]["items"]
        for res_status, resp_page_data in results:
            if isinstance(resp_page_data, Exception): # Should be caught by gather if not return_exceptions=True
                # This path might not be hit if _api_request itself raises on error
                logger.error(f"Erro em uma das solicitações de paginação de selo: {resp_page_data}")
                continue # Or raise, depending on desired strictness

            if res_status != 200:
                logger.warning(
                    f"Erro ao buscar página de álbuns do selo {label_id} (status: {res_status}): {resp_page_data.get('message')}"
                )
                continue # Skip this page

            page_items = resp_page_data.get("albums", {}).get("items")
            if page_items:
                current_items.extend(page_items)

        return label_resp_data

    async def search(self, media_type: str, query: str, limit: int = 500) -> list[dict]:
        if media_type not in ("artist", "album", "track", "playlist"):
            raise QobuzAPIError(f"Tipo de mídia '{media_type}' não disponível para pesquisa no Qobuz.")

        params = {
            "query": query,
        }
        epoint = f"{media_type}/search"

        return await self._paginate(epoint, params, limit=limit)

    async def get_featured(self, query, limit: int = 500) -> list[dict]:
        params = {
            "type": query,
        }
        if query not in QOBUZ_FEATURED_KEYS:
            raise QobuzAPIError(f'Query de destaque inválida: "{query}". Chaves válidas: {QOBUZ_FEATURED_KEYS}')
        epoint = "album/getFeatured"
        return await self._paginate(epoint, params, limit=limit)

    async def get_user_favorites(self, media_type: str, limit: int = 500) -> list[dict]:
        if media_type not in ("track", "artist", "album"):
            raise QobuzAPIError(f"Tipo de mídia '{media_type}' inválido para buscar favoritos do usuário no Qobuz.")
        params = {"type": f"{media_type}s"}
        epoint = "favorite/getUserFavorites"

        return await self._paginate(epoint, params, limit=limit)

    async def get_user_playlists(self, limit: int = 500) -> list[dict]:
        epoint = "playlist/getUserPlaylists"
        return await self._paginate(epoint, {}, limit=limit)

    async def get_downloadable(self, item: str, quality: int) -> Downloadable:
        if not self.logged_in:
            raise AuthenticationError("Não está logado no Qobuz.", item=item)
        if self.secret is None:
            raise ClientError("Segredo do cliente Qobuz não inicializado.", item=item)
        if not (1 <= quality <= self.max_quality): # Use self.max_quality
            raise ValueError(f"Qualidade inválida: {quality}. Deve estar entre 1 e {self.max_quality}.", item=item)

        status, resp_data = await self._request_file_url(item, quality, self.secret)

        if status == 401:
             raise AuthenticationError("Não autorizado a obter URL de arquivo do Qobuz (token/segredo pode ter expirado ou ser inválido).", item=item)
        if status == 403:
            message = resp_data.get("message", "Proibido obter URL do arquivo (provavelmente restrições regionais/direitos).")
            raise NonStreamableError(message, item=item)
        if status == 404:
            raise ResourceNotFoundError(f"Faixa ID {item} não encontrada para download no Qobuz.", item=item)
        if status != 200:
            message = resp_data.get("message", f"Erro desconhecido ({status}) ao solicitar URL do arquivo para faixa ID {item}.")
            raise QobuzAPIError(message, item=item)

        if not isinstance(resp_data, dict):
            raise InvalidAPIResponseError(f"Resposta de URL de arquivo inesperada (não é um dicionário) para faixa ID {item}.", item=item)

        stream_url = resp_data.get("url")
        if not stream_url: # Check if None or empty string
            restrictions = resp_data.get("restrictions")
            if isinstance(restrictions, list) and restrictions and isinstance(restrictions[0], dict) and restrictions[0].get("code"):
                words = re.findall(r"([A-Z][a-z]+)", restrictions[0]["code"])
                message = (words[0] + " " + " ".join(map(str.lower, words[1:])) + "."
                           if words else f"Restrição desconhecida: {restrictions[0]['code']}")
                raise NonStreamableError(message, item=item)
            raise InvalidAPIResponseError("URL de stream não encontrada ou vazia na resposta da API do Qobuz.", item=item)

        return BasicDownloadable(
            self.session, stream_url, "flac" if quality > 1 else "mp3", source="qobuz"
        )

    async def _paginate(
        self,
        epoint: str,
        params: dict,
        limit: int = 500,
    ) -> list[dict]:
        """Paginate search results.

        params:
            limit: If None, all the results are yielded. Otherwise a maximum
            of `limit` results are yielded.

        Returns
        -------
            Generator that yields (status code, response) tuples
        """
        params.update({"limit": limit if limit is not None else 500}) # Ensure limit is set
        status, initial_page_data = await self._api_request(epoint, params)

        if status == 404 and epoint.endswith("/search"):
            logger.debug(f"Pesquisa para '{params.get('query')}' em '{epoint}' não retornou resultados (404).")
            return []
        if status != 200:
            message = initial_page_data.get("message", f"Erro ao buscar a primeira página de '{epoint}' (status: {status}).")
            raise QobuzAPIError(message, item=params)

        logger.debug("paginate: initial request made with status %d for %s", status, epoint)

        key = epoint.split("/")[0] + "s"
        items_section = initial_page_data.get(key) # Ensure this is a dict
        if not isinstance(items_section, dict):
            raise InvalidAPIResponseError(
                f"Seção '{key}' esperada na resposta da API do Qobuz não é um dicionário ou está ausente para {epoint}.",
                item=params
            )

        total_items_available = items_section.get("total", 0)
        effective_total_to_fetch = total_items_available
        if limit is not None and limit < total_items_available:
            effective_total_to_fetch = limit

        logger.debug(f"paginate: {effective_total_to_fetch} total items to fetch for {epoint}")

        if effective_total_to_fetch == 0:
            logger.debug(f"Nenhum item encontrado para {epoint} com os parâmetros {params}")
            return []

        api_page_limit = int(items_section.get("limit", 500)) # API's limit per page
        current_offset = int(items_section.get("offset", 0)) # Initial offset from first response

        all_pages_data = [initial_page_data]

        # Number of items received in the first page
        num_items_in_first_page = len(items_section.get("items", []))

        # Update offset for the next potential request
        # current_offset should be the starting point for the next fetch
        current_offset += num_items_in_first_page

        api_requests_coroutines = []
        while current_offset < effective_total_to_fetch and current_offset < total_items_available:
            params_for_next_page = params.copy()
            params_for_next_page["offset"] = current_offset

            items_remaining_to_fetch_overall = effective_total_to_fetch - current_offset
            params_for_next_page["limit"] = min(api_page_limit, items_remaining_to_fetch_overall)

            if params_for_next_page["limit"] <= 0: # Should not happen if logic is correct
                break

            api_requests_coroutines.append(self._api_request(epoint, params_for_next_page))
            current_offset += params_for_next_page["limit"]

        if api_requests_coroutines:
            # Gathers (status, data) tuples or exceptions if _api_request raises them
            page_results_tuples = await asyncio.gather(*api_requests_coroutines, return_exceptions=True)
            for result_item in page_results_tuples:
                if isinstance(result_item, Exception):
                    # If _api_request now raises on error, this path will catch it
                    logger.error(f"Erro em uma solicitação de paginação para {epoint}: {result_item}", exc_info=True)
                    # Depending on strictness, either continue or re-raise/collect errors
                    # For now, we log and try to get as many pages as possible
                    continue

                # Unpack tuple if not an exception
                result_status, page_data = result_item
                if result_status != 200:
                    logger.warning(
                        f"Erro ao buscar página para {epoint} (status: {result_status}): {page_data.get('message')}"
                    )
                    continue
                all_pages_data.append(page_data)

        return all_pages_data

    async def _get_app_id_and_secrets(self) -> tuple[str, list[str]]:
        async with QobuzSpoofer(
            verify_ssl=self.config.session.downloads.verify_ssl
        ) as spoofer:
            return await spoofer.get_app_id_and_secrets()

    async def _test_secret(self, secret: str) -> Optional[str]:
        # Test with a known public track ID that is generally available
        # Using a low quality (MP3) for testing might be more reliable if high-quality formats have stricter checks
        test_track_id = "19512574" # Example: a known public domain or widely available track
        test_quality = 1 # MP3 quality, often format_id 5 for Qobuz

        try:
            status, resp_data = await self._request_file_url(test_track_id, test_quality, secret)
            # A 400 Bad Request might indicate the secret itself is malformed or rejected by the signing process
            if status == 400:
                logger.debug(f"Segredo do Qobuz resultou em 400 Bad Request: {secret[:10]}...")
                return None
            # 200 OK means the URL was generated, secret is likely valid
            # 401 Unauthorized might also mean the secret is valid but the UAT is bad or the specific track is restricted
            # For testing the secret itself, 200 is the primary success indicator.
            # If we get 401, it's ambiguous whether it's the secret or UAT.
            # However, Qobuz often uses 401 for bad signatures too.
            if status == 200:
                logger.debug(f"Segredo do Qobuz validado com sucesso: {secret[:10]}...")
                return secret
            # If status is 401, it could be the secret or the UAT.
            # Let's assume for secret testing, 401 is a potential positive if not 400.
            # The original code treated 401 as potentially valid.
            if status == 401:
                 logger.warning(f"Segredo do Qobuz resultou em 401 Unauthorized (pode ser válido, mas UAT/permissões são um problema): {secret[:10]}...")
                 return secret # Tentatively accept, _get_valid_secret will pick the first one that doesn't return None

            logger.warning(f"Teste de segredo do Qobuz com status {status} para {secret[:10]}... Resposta: {resp_data}")
            return None # Other statuses are likely failures for the secret itself
        except QobuzAPIError as e: # Catch errors from _request_file_url itself
            logger.warning(f"Erro de API ao testar o segredo do Qobuz {secret[:10]}...: {e}")
            return None
        except Exception as e: # Catch any other unexpected error during secret test
            logger.error(f"Erro inesperado ao testar o segredo do Qobuz {secret[:10]}...: {e}", exc_info=True)
            return None


    async def _get_valid_secret(self, secrets: list[str]) -> str:
        if not secrets:
            raise InvalidAppSecretError("Nenhum segredo do Qobuz fornecido para validação.")

        # Test secrets one by one to find the first working one.
        # asyncio.gather might be too aggressive if many secrets are invalid and cause rate limiting.
        for secret in secrets:
            if await self._test_secret(secret):
                return secret

        # If no secret worked after individual tests
        raise InvalidAppSecretError(
            "Nenhum dos segredos do Qobuz fornecidos é válido ou o teste falhou."
            f" Segredos testados (parcial): {[s[:10] + '...' for s in secrets]}"
        )


    async def _request_file_url(
        self,
        track_id: str,
        quality: int,
        secret: str,
    ) -> tuple[int, dict]:
        quality = self.get_quality(quality)
        unix_ts = time.time()
        r_sig = f"trackgetFileUrlformat_id{quality}intentstreamtrack_id{track_id}{unix_ts}{secret}"
        logger.debug("Raw request signature: %s", r_sig)
        r_sig_hashed = hashlib.md5(r_sig.encode("utf-8")).hexdigest()
        logger.debug("Hashed request signature: %s", r_sig_hashed)
        params = {
            "request_ts": unix_ts,
            "request_sig": r_sig_hashed,
            "track_id": track_id,
            "format_id": quality,
            "intent": "stream",
        }
        return await self._api_request("track/getFileUrl", params)

    async def _api_request(self, epoint: str, params: dict) -> tuple[int, dict]:
        """Make a request to the API.
        returns: status code, json parsed response
        """
        url = f"{QOBUZ_BASE_URL}/{epoint}"
        item_id_for_logging = params.get("track_id") or params.get(f"{epoint.split('/')[0]}_id")

        current_retry = 0
        while True:
            logger.debug("api_request: endpoint=%s, params=%s, attempt=%d", epoint, params, current_retry + 1)
            try:
                async with self.rate_limiter:
                    async with self.session.get(url, params=params) as response:
                        try:
                            resp_json = await response.json()
                        except aiohttp.ContentTypeError:
                            resp_text = await response.text()
                            resp_json = {"message": resp_text[:200]}
                            logger.warning(
                                f"Resposta não-JSON da API Qobuz para {epoint} (status {response.status}): {resp_text[:100]}"
                            )

                        if response.status == 429: # Rate limit
                            # Qobuz might not send Retry-After, so use exponential backoff
                            delay = (self.initial_retry_delay * (2**current_retry)) + (hashlib.md5(str(params).encode()).digest()[0] / 255.0) # Add jitter
                            logger.warning(
                                f"Limite de taxa da API Qobuz atingido para {epoint} (status 429). "
                                f"Tentando novamente em {delay:.2f}s... (tentativa {current_retry + 1}/{self.max_retries})"
                            )
                            if current_retry < self.max_retries:
                                await asyncio.sleep(delay)
                                current_retry += 1
                                continue # Retry the request
                            else:
                                raise APILimitError(
                                    f"Limite de taxa da API Qobuz excedido para {epoint} após {self.max_retries} tentativas.",
                                    item=item_id_for_logging
                                )

                        if response.status != 200:
                             logger.debug(
                                f"API Qobuz {epoint} respondeu com status {response.status}. "
                                f"Params: {params}. Resposta: {resp_json}"
                             )
                        return response.status, resp_json

            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError, aiohttp.ClientOSError) as e:
                logger.warning(
                    f"Erro de conexão/rede com API Qobuz ({epoint}): {e}. "
                    f"Tentando novamente em {self.initial_retry_delay * (2**current_retry):.2f}s... "
                    f"(tentativa {current_retry + 1}/{self.max_retries})",
                    item=item_id_for_logging
                )
                if current_retry < self.max_retries:
                    await asyncio.sleep(self.initial_retry_delay * (2**current_retry))
                    current_retry += 1
                    continue # Retry
                raise NetworkError(f"Erro de conexão com API Qobuz ({epoint}) após {self.max_retries} tentativas: {e}", item=item_id_for_logging) from e
            except asyncio.TimeoutError as e:
                logger.warning(
                    f"Timeout ao conectar com API Qobuz ({epoint}). "
                    f"Tentando novamente em {self.initial_retry_delay * (2**current_retry):.2f}s... "
                    f"(tentativa {current_retry + 1}/{self.max_retries})",
                    item=item_id_for_logging
                )
                if current_retry < self.max_retries:
                    await asyncio.sleep(self.initial_retry_delay * (2**current_retry))
                    current_retry += 1
                    continue # Retry
                raise NetworkError(f"Timeout ao conectar com API Qobuz ({epoint}) após {self.max_retries} tentativas.", item=item_id_for_logging) from e
            except aiohttp.ClientError as e: # Catch other aiohttp client errors
                # For other client errors, might not be safe to retry, raise directly
                raise NetworkError(f"Erro de cliente HTTP com API Qobuz ({epoint}): {e}", item=item_id_for_logging) from e
            # If we reach here, it means a successful response or an unhandled error that should propagate

    @staticmethod
    def get_quality(quality: int):
        quality_map = (5, 6, 7, 27)
        return quality_map[quality - 1]
