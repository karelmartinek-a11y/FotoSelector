class CloudProviderError(Exception):
    """Základní chyba cloudové vrstvy."""


class CloudAuthError(CloudProviderError):
    """Přihlášení selhalo nebo chybí platný token."""


class CloudConfigurationError(CloudProviderError):
    """Provider nemá potřebnou lokální konfiguraci."""


class CloudRateLimitError(CloudProviderError):
    """Provider dočasně omezuje počet požadavků."""


class CloudUnavailableError(CloudProviderError):
    """Zdroj nebo účet momentálně není dostupný."""


class CloudUserActionRequired(CloudProviderError):
    """Je potřeba zásah uživatele, například otevření pickeru."""
