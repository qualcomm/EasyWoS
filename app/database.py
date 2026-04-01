"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
from asyncio import current_task
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import async_scoped_session

Base = declarative_base()


class SanicDb(object):

    def __init__(self):
        pass

    def init_app(self, app):
        self.conn = None
        self.engine = None

        @app.listener('before_server_start')
        async def db_conn(app, loop):
            engine = create_async_engine(
                url=app.config['DB_URL'],
                echo=True
                # pool_size=app.config['POOL_SIZE'],
                # max_overflow=app.config['OVER_SIZE'],
                # pool_recycle=app.config['RECYCLE']
            )
            async with engine.begin() as conn:
                if app.config['DROP_ALL']:
                    await conn.run_sync(Base.metadata.drop_all)
                if app.config['CREATE_ALL']:
                    await conn.run_sync(Base.metadata.create_all)
            async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            self.conn = async_scoped_session(async_session, scopefunc=current_task)
            self.engine = engine

        @app.listener('after_server_stop')
        async def db_conn_stop(app, loop):
            await self.conn.remove()
            await self.engine.dispose()


db = SanicDb()
