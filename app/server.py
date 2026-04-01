"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
from sanic import Sanic, response
# from sanic.response import text
# from sanic_ext import Extend
from sanic.exceptions import NotFound

from app.database import db
from app.log import log
from app.jwt import auth
from easywos.api_v1 import api_v1
from easywos.front import page
import settings

def create_app() -> Sanic:
    app = Sanic('EasyWoS')
    app.static('/', 'dist')
    app.ext.openapi.add_security_scheme(
        "token",
        "http",
        scheme="bearer",
        bearer_format="JWT"
    )

    # app.update_config("./settings.py")
    # when we use cython to compile .py to .so, setting.py like below is used
    app.config.update_config(settings)

    @app.exception(NotFound)
    async def handle_404_redirect(request, exception):
        return await response.file("dist/index.html")

    db.init_app(app)
    log.init_app(app)
    auth.init_app(app)

    app.blueprint([api_v1, page])

    return app
