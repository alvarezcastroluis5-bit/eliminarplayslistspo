import urllib.parse
from bottle import abort, redirect, request, response, route, run, template

CLIENT_ID = "32931330adc34dfd9c0cca8cc952ca75"
CLIENT_SECRET = "326e4e515782418d812376d610b5c46f"

SCOPE = (
    "user-library-read "
    "user-library-modify "
    "playlist-read-private "
    "playlist-modify-private "
    "playlist-modify-public "
    "user-follow-read "
    "user-follow-modify"
)

REDIRECT_URI = "http://127.0.0.1:8080/callback"
BASE_URL = "https://api.spotify.com/v1"
RESPONSE_ITEMS_LIMIT = 50

TEMPLATE_AUTH_KWARGS = {
    "CLIENT_ID": CLIENT_ID,
    "REDIRECT_URI": REDIRECT_URI,
    "SCOPE": SCOPE,
}


def _get_auth_url():
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "show_dialog": "true",
    }
    return "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)


def _get_access_token():
    access_token = request.get_cookie("access_token")
    if access_token is None:
        redirect("/")
    return access_token


def _spotify_request(method, url, access_token, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {access_token}"
    res = requests.request(method, url, headers=headers, **kwargs)

    if res.status_code not in (200, 201, 202, 204):
        try:
            data = res.json()
            message = (
                data.get("error", {}).get("message")
                or data.get("error_description")
                or str(data)
            )
        except Exception:
            message = res.text
        abort(res.status_code, message)

    if res.status_code == 204 or not res.text:
        return None

    return res.json()


@route("/")
def main():
    return template(
        "home",
        auth_url=_get_auth_url(),
        **TEMPLATE_AUTH_KWARGS,
    )


@route("/callback")
def callback():
    code = request.query.code

    if code is None:
        abort(401, "Error: code not provided")

    res = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    )

    if res.status_code != 200:
        try:
            error = res.json().get("error_description", res.text)
        except Exception:
            error = res.text
        abort(res.status_code, error)

    data = res.json()

    response.set_cookie("access_token", data["access_token"], path="/")
    response.set_cookie("refresh_token", data.get("refresh_token", ""), path="/")

    redirect("/")


@route("/logout")
def logout():
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    redirect("/")


def _get_items(access_token, item_type):
    items = []
    offset = 0

    while True:
        data = _spotify_request(
            "GET",
            f"{BASE_URL}/me/{item_type}?limit={RESPONSE_ITEMS_LIMIT}&offset={offset}",
            access_token,
        )

        batch = data.get("items", [])
        items.extend(batch)

        total = data.get("total", 0)
        offset += RESPONSE_ITEMS_LIMIT

        if offset >= total or not batch:
            break

    return items


@route("/get-liked-songs")
def get_liked_songs():
    access_token = _get_access_token()
    tracks = _get_items(access_token, "tracks")

    return template(
        "home",
        auth_url=_get_auth_url(),
        tracks=tracks,
        **TEMPLATE_AUTH_KWARGS,
    )


@route("/get-saved-albums")
def get_saved_albums():
    access_token = _get_access_token()
    albums = _get_items(access_token, "albums")

    return template(
        "home",
        auth_url=_get_auth_url(),
        albums=albums,
        **TEMPLATE_AUTH_KWARGS,
    )


@route("/get-playlists")
def get_playlists():
    access_token = _get_access_token()
    playlists = _get_items(access_token, "playlists")

    return template(
        "home",
        auth_url=_get_auth_url(),
        playlists=playlists,
        **TEMPLATE_AUTH_KWARGS,
    )


@route("/get-podcasts")
def get_podcasts():
    access_token = _get_access_token()
    shows = _get_items(access_token, "shows")

    return template(
        "home",
        auth_url=_get_auth_url(),
        shows=shows,
        **TEMPLATE_AUTH_KWARGS,
    )


@route("/delete", method="POST")
def delete():
    access_token = _get_access_token()
    item_type = request.query.item_type
    redirect_to = request.query.redirect_to or ""

    allowed_types = {"tracks", "albums", "shows", "playlists"}

    if item_type not in allowed_types:
        abort(400, "Tipo de elemento no permitido")

    ids = request.forms.getall(item_type)

    if not ids:
        redirect(f"/{redirect_to}")

    if item_type == "playlists":
        for playlist_id in ids:
            _spotify_request(
                "DELETE",
                f"{BASE_URL}/playlists/{playlist_id}/followers",
                access_token,
            )
    else:
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]

            _spotify_request(
                "DELETE",
                f"{BASE_URL}/me/{item_type}?ids={','.join(chunk)}",
                access_token,
            )

    redirect(f"/{redirect_to}")


if __name__ == "__main__":
    run(host="127.0.0.1", port=8080, debug=True, reloader=True)
