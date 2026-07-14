from requests_oauthlib import OAuth2Session

AUTHORIZE_URL = "https://anilist.co/api/v2/oauth/authorize"
TOKEN_URL = "https://anilist.co/api/v2/oauth/token"


def get_authorization_url(client_id: str, redirect_uri: str) -> tuple[str, str]:
    """Return (authorization_url, state) for the AniList OAuth2 flow."""
    session = OAuth2Session(client_id, redirect_uri=redirect_uri)
    authorization_url, state = session.authorization_url(AUTHORIZE_URL)
    return authorization_url, state


def fetch_token(client_id: str, client_secret: str, redirect_uri: str,
                authorization_response: str) -> dict:
    """Exchange an authorization code for an access token."""
    session = OAuth2Session(client_id, redirect_uri=redirect_uri)
    return session.fetch_token(
        TOKEN_URL,
        client_secret=client_secret,
        authorization_response=authorization_response,
    )
