"""Registry các OAuth provider. Thêm nền tảng mới chỉ cần register_provider()."""
from app.services.oauth.base import OAuthProvider
from app.services.oauth.threads import ThreadsOAuthProvider

_PROVIDERS: dict[str, OAuthProvider] = {
    "threads": ThreadsOAuthProvider(),
}


def get_provider(name: str) -> OAuthProvider:
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise KeyError(f"Chưa đăng ký OAuth provider cho '{name}'")
    return provider


def register_provider(provider: OAuthProvider) -> None:
    _PROVIDERS[provider.name] = provider
