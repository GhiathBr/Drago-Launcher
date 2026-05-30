# auth.py
# Python 3.11+
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import aiohttp


LIVE_AUTHORIZE_URL = "https://login.live.com/oauth20_authorize.srf"
LIVE_TOKEN_URL = "https://login.live.com/oauth20_token.srf"
XBL_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_AUTH_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"


class AuthError(Exception):
    pass


class TokenExpiredError(AuthError):
    pass


@dataclass(slots=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None
    expires_at: float  # epoch seconds


@dataclass(slots=True)
class XSTSResult:
    user_token: str   # XSTS token (JWT)
    xuid: str
    uhs: str


class XSTSIdentityManager:
    def __init__(
        self,
        client_id: str,
        redirect_uri: str = "https://login.live.com/oauth20_desktop.srf",
        scope: str = "XboxLive.signin offline_access",
        relying_party: str = "rp://api.minecraftservices.com/",
        sandbox_id: str = "RETAIL",
        timeout_s: float = 10.0,
    ) -> None:
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.scope = scope
        self.relying_party = relying_party
        self.sandbox_id = sandbox_id
        self.timeout = aiohttp.ClientTimeout(total=timeout_s)

    def authorization_url(self, state: str = "drago-bridge") -> str:
        q = urlencode(
            {
                "client_id": self.client_id,
                "response_type": "code",
                "redirect_uri": self.redirect_uri,
                "scope": self.scope,
                "state": state,
            }
        )
        return f"{LIVE_AUTHORIZE_URL}?{q}"

    async def exchange_code_for_oauth(self, code: str) -> OAuthTokens:
        payload = {
            "client_id": self.client_id,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
        }
        data = await self._post_form(LIVE_TOKEN_URL, payload)
        return self._parse_oauth_tokens(data)

    async def refresh_oauth(self, refresh_token: str) -> OAuthTokens:
        payload = {
            "client_id": self.client_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
        }
        try:
            data = await self._post_form(LIVE_TOKEN_URL, payload)
        except TokenExpiredError:
            raise
        except AuthError as e:
            # Treat invalid_grant or similar as refresh token expiry
            if "invalid_grant" in str(e).lower():
                raise TokenExpiredError("Refresh token expired or revoked.") from e
            raise
        return self._parse_oauth_tokens(data)

    async def get_xsts(self, oauth: OAuthTokens) -> XSTSResult:
        # Refresh if already expired
        if oauth.expires_at <= time.time():
            if not oauth.refresh_token:
                raise TokenExpiredError("Access token expired and no refresh token available.")
            oauth = await self.refresh_oauth(oauth.refresh_token)

        xbl = await self._exchange_for_xbl(oauth.access_token)
        return await self._exchange_for_xsts(xbl["token"])

    async def start_device_authorization(self) -> dict[str, Any]:
        """Start the device code flow and return the user code and verification URI."""
        if not self.client_id or not isinstance(self.client_id, str):
            raise ValueError("A valid Client ID string must be present to initiate device authorization.")
            
        url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
        return await self._post_form(url, {
            "client_id": self.client_id,
            "scope": self.scope
        })

    async def poll_device_authorization(self, device_code: str, interval: int) -> OAuthTokens:
        """Poll the token endpoint until the user completes the device authentication."""
        url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
        payload = {
            "client_id": self.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code
        }
        
        while True:
            try:
                data = await self._post_form(url, payload)
                return OAuthTokens(
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token"),
                    expires_at=time.time() + data.get("expires_in", 3600)
                )
            except AuthError as e:
                if "authorization_pending" in str(e):
                    await asyncio.sleep(interval)
                elif "expired_token" in str(e):
                    raise AuthError("The device code has expired. Please try again.") from e
                else:
                    raise e

    async def get_minecraft_profile(self, oauth: OAuthTokens) -> tuple[str, dict]:
        """Gets the Xbox token and then fetches the Minecraft token and profile."""
        xbl = await self._exchange_for_xbl(oauth.access_token)
        xsts = await self._exchange_for_xsts(xbl["token"])
        
        # Authenticate with Minecraft using XSTS token
        mc_auth_url = "https://api.minecraftservices.com/authentication/login_with_xbox"
        mc_auth_payload = {
            "identityToken": f"XBL3.0 x={xsts.uhs};{xsts.user_token}"
        }
        mc_data = await self._post_json(mc_auth_url, mc_auth_payload)
        mc_access_token = mc_data["access_token"]
        
        # Get Minecraft profile
        profile_url = "https://api.minecraftservices.com/minecraft/profile"
        async with aiohttp.ClientSession() as session:
            async with session.get(profile_url, headers={"Authorization": f"Bearer {mc_access_token}"}) as r:
                if r.status != 200:
                    raise AuthError(f"Failed to fetch Minecraft profile: {r.status}")
                profile = await r.json()
                
        return mc_access_token, profile

    async def authenticate(
        self,
        *,
        auth_code: str | None = None,
        refresh_token: str | None = None,
    ) -> tuple[OAuthTokens, XSTSResult]:
        if not auth_code and not refresh_token:
            raise ValueError("Provide either auth_code or refresh_token.")

        oauth = (
            await self.exchange_code_for_oauth(auth_code)  # type: ignore[arg-type]
            if auth_code
            else await self.refresh_oauth(refresh_token)    # type: ignore[arg-type]
        )
        xsts = await self.get_xsts(oauth)
        return oauth, xsts

    async def _exchange_for_xbl(self, access_token: str) -> dict[str, Any]:
        payload = {
            "Properties": {
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": f"d={access_token}",
            },
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT",
        }
        data = await self._post_json(XBL_AUTH_URL, payload, headers={"x-xbl-contract-version": "1"})
        try:
            token = data["Token"]
            uhs = data["DisplayClaims"]["xui"][0]["uhs"]
        except (KeyError, IndexError, TypeError) as e:
            raise AuthError(f"Malformed XBL response: {data}") from e
        return {"token": token, "uhs": uhs}

    async def _exchange_for_xsts(self, xbl_token: str) -> XSTSResult:
        payload = {
            "Properties": {"SandboxId": self.sandbox_id, "UserTokens": [xbl_token]},
            "RelyingParty": self.relying_party,
            "TokenType": "JWT",
        }
        data = await self._post_json(XSTS_AUTH_URL, payload, headers={"x-xbl-contract-version": "1"})
        try:
            user_token = data["Token"]
            xui = data.get("DisplayClaims", {}).get("xui", [{}])[0]
            xuid = xui.get("xid", "")  # Often absent depending on account type/Xbox profile creation
            uhs = xui.get("uhs", "")
        except (KeyError, IndexError, TypeError) as e:
            raise AuthError(f"Malformed XSTS response: {data}") from e
        return XSTSResult(user_token=user_token, xuid=xuid, uhs=uhs)

    async def _post_form(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with aiohttp.ClientSession(timeout=self.timeout) as s:
            async with s.post(url, data=payload) as r:
                body = await r.json(content_type=None)
                if r.status >= 400:
                    error = body.get("error") if isinstance(body, dict) else None
                    if error in {"invalid_grant", "token_expired"}:
                        raise TokenExpiredError(f"OAuth token expired/revoked: {body}")
                    raise AuthError(f"HTTP {r.status} @ {url}: {body}")
                return body

    async def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
        async with aiohttp.ClientSession(timeout=self.timeout) as s:
            async with s.post(url, json=payload, headers=headers) as r:
                body = await r.json(content_type=None)
                if r.status >= 400:
                    if isinstance(body, dict) and "XErr" in body:
                        raise AuthError(f"XSTS/XBL error XErr={body.get('XErr')}: {body.get('Message', body)}")
                    raise AuthError(f"HTTP {r.status} @ {url}: {body}")
                return body


# ---- Example CLI usage ----
# pip install aiohttp
# (The Client ID is baked in safely for public desktop client usage)
if __name__ == "__main__":
    import os

    async def main() -> None:
        client_id = "ab5dd215-1a94-4383-a5f2-d51d42ab758f"
        
        auth_code = os.getenv("MS_AUTH_CODE")
        refresh_token = os.getenv("MS_REFRESH_TOKEN")

        mgr = XSTSIdentityManager(client_id=client_id)

        if not auth_code and not refresh_token:
            print("Open this URL, sign in, then copy the `code` query param from redirect URL:")
            print(mgr.authorization_url())
            return

        oauth, xsts = await mgr.authenticate(auth_code=auth_code, refresh_token=refresh_token)

        print("UserToken:", xsts.user_token)
        print("XUID:", xsts.xuid)
        print("UHS:", xsts.uhs)
        print("ExpiresAt:", int(oauth.expires_at))
        if oauth.refresh_token:
            print("RefreshToken:", oauth.refresh_token)

    asyncio.run(main())