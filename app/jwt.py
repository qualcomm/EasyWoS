from sanic_jwt import initialize
from helper.auth_helper import authenticate, retrieve_user, AuthResponses


class SanicJwt(object):

    def __init__(self):
        pass

    def init_app(self, app):
        initialize(
            app,
            authenticate=authenticate,
            retrieve_user=retrieve_user,
            url_prefix='/api/authentication',
            responses_class=AuthResponses,
            secret=app.config['JWT_SECRET_KEY'],
            expiration_delta=app.config['JWT_EXPIRATION_DELTA']
        )


auth = SanicJwt()
