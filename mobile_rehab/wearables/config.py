"""Credentials are environment-only, never shipped in APK or exposed in capabilities."""
from dataclasses import dataclass
import os
from urllib.parse import urlsplit
from .contracts import SCOPES, zone


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    enabled: bool = False
    client_id: str = ''
    client_secret: str = ''
    redirect_uri: str = ''
    approved_scopes: tuple = ()
    timezone: str = ''
    region: str = ''
    api_version: str = ''
    subscription_enabled: bool = False

    def reason(self):
        if not self.enabled or not all((self.client_id, self.client_secret, self.redirect_uri, self.timezone)):
            return 'PROVIDER_NOT_CONFIGURED'
        uri = urlsplit(self.redirect_uri)
        if (uri.scheme != 'https' or not uri.hostname or uri.username or uri.query or uri.fragment
                or uri.path != '/api/health/oauth/' + self.provider + '/callback'):
            return 'REDIRECT_URI_INVALID'
        try:
            zone(self.timezone)
        except Exception:
            return 'TIMEZONE_REQUIRED'
        if not any(s in self.approved_scopes for s in SCOPES[self.provider].values()):
            return 'APPROVAL_PENDING'
        if self.provider == 'huawei' and (self.region != 'CN' or not self.api_version or '*' in self.api_version):
            return 'VENDOR_CONTRACT_REQUIRED'
        return None


def load_config(env=None):
    env = os.environ if env is None else env
    on = env.get('ANKANG_HEALTH_ENABLED') == '1'
    result = {}
    for provider in SCOPES:
        prefix = provider.upper()
        result[provider] = ProviderConfig(provider, on and env.get(prefix + '_CLOUD_ENABLED') == '1',
            env.get(prefix + '_CLIENT_ID', ''), env.get(prefix + '_CLIENT_SECRET', ''),
            env.get(prefix + '_REDIRECT_URI', ''), tuple(env.get(prefix + '_APPROVED_SCOPES', '').split()),
            env.get(prefix + '_TIMEZONE', ''), env.get(prefix + '_API_REGION', ''),
            env.get(prefix + '_API_VERSION', ''), env.get(prefix + '_SUBSCRIPTION_ENABLED') == '1')
    return result
