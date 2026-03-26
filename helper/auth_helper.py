from sanic_jwt import exceptions
from sanic_jwt import Responses

from helper.user_helper import find_user_exists
from app.log import log

async def authenticate(request, *args, **kwargs):
    log.logger.debug(f"authenticate request={request}")
    username = request.json.get("username", None)
    password = request.json.get("password", None)
    if not username or not password:
        raise exceptions.AuthenticationFailed("Missing username or password.")

    user = await find_user_exists(username)
    if user is None:
        raise exceptions.AuthenticationFailed("User not found.")
    if user.status is False:
        raise exceptions.AuthenticationFailed("User unavailable.")

    if not user.check_password(password):
        raise exceptions.AuthenticationFailed("Password is incorrect.")

    return user


async def retrieve_user(request, payload, *args, **kwargs) -> dict:
    """
    :param request:
    :param payload:
    :param args:
    :param kwargs:
    :return:
    """
    username = request.args.get('username')
    log.logger.debug(f"retrieve_user username={username} request={request} payload={payload}")
    user = await find_user_exists(username)
    if not user:
        return {}
    columns = [
        'username', 'status'
    ]
    return user.serialize(columns=columns)


class AuthResponses(Responses):
    """
    额外的返回 在playload外的
    """
    @staticmethod
    def extend_authenticate(request,
                            user=None,
                            access_token=None,
                            refresh_token=None):
        """
        /auth接口
        """
        columns = [
            'username', 'status'
        ]
        return {
            "user": user.serialize(columns=columns)
        }

    # @staticmethod
    # def extend_retrieve_user(request, user=None, payload=None):
    #     """
    #     这个是/auth/me接口的 在retrieve_user之后执行
    #     """
    #     return {"user": user, "payload": payload}

    @staticmethod
    def extend_verify(request, user=None, payload=None):
        """
        /auth/verify
        """
        return {}

    @staticmethod
    def extend_refresh(request,
                       user=None,
                       access_token=None,
                       refresh_token=None,
                       purported_token=None,
                       payload=None):
        return {}
