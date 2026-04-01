"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
import datetime
from sqlalchemy import INTEGER, Column, DateTime, select, delete, func
from sqlalchemy.exc import IntegrityError

from app.log import log
from app.database import Base, db
from util.common import string_toDatetime, datetime_toString


class BaseModel(Base):
    __abstract__ = True
    __table_args__ = {'sqlite_autoincrement': True}

    id = Column(INTEGER, primary_key=True)
    createtime = Column(DateTime, default=datetime.datetime.utcnow, comment='create time')
    updatetime = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, comment='update time')

    def autoset(self, data=None, filter=[]):
        if data:
            for i in self.__table__.columns:
                if i.name in filter:
                    continue
                v = data.get(i.name)
                if v is not None:
                    self.__setattr__(i.name, v)
        return self

    def to_dict(self):
        res = dict()
        for i in self.__table__.columns:
            v = getattr(self, i.name)
            res[i.name] = v
            if isinstance(v, datetime.datetime):
                res[i.name] = datetime_toString(v)
        return res

    def serialize(self, columns=[]):
        res = dict()
        columns += ['id', 'createtime', 'updatetime']
        for column in self.__table__.columns:
            if column.name in columns:
                value = getattr(self, column.name)
                res[column.name] = value
                if isinstance(value, datetime.datetime):
                    res[column.name] = value.strftime("%Y-%m-%d %H:%M:%S")
        return res

    async def update(self, data=None):
        async with db.conn() as session:
            res = await session.merge(self.autoset(data))
            await session.commit()
        return res

    async def save(self, data=None):
        async with db.conn() as session:
            try:
                session.add(self.autoset(data))
                await session.commit()
            except IntegrityError as e:
                log.logger.error(str(e.orig))
                await session.rollback()
                return None, str(e.orig), 409
            except Exception as e:
                log.logger.error(str(e))
                await session.rollback()
                return None, str(e), 500
        return self, 'success', 200

    @classmethod
    async def query(cls, *conditions):
        async with db.conn() as session:
            results = (await session.execute(select(cls).where(*conditions))).scalars()
        return [result for result in results]

    @classmethod
    async def delete(cls, *condition):
        async with db.conn() as session:
            await session.execute(delete(cls).where(*condition))
            await session.commit()

    @classmethod
    async def query_page(cls, page_num, page_size, condition=None, desc=False, columns=None):
        total_orm = select(func.count(cls.id))
        data_orm = select(cls)
        condition_list = []

        if condition:
            start_time = condition.pop('start_time', None)
            end_time = condition.pop('end_time', None)
            if start_time:
                start_time = string_toDatetime(start_time)
                condition_list.append(cls.createtime >= start_time)
            if end_time:
                end_time = string_toDatetime(end_time)
                condition_list.append(cls.createtime <= end_time)

            query_list = set(condition) & set([column.name for column in cls.__table__.columns])
            for i in query_list:
                v = condition.get(i)
                if isinstance(v, str) and ',' in v:
                    condition_list.append(getattr(cls, i).in_(v.split(',')))
                else:
                    condition_list.append(getattr(cls, i) == v)

        if len(condition_list) > 0:
            total_orm = total_orm.where(*condition_list)
            data_orm = data_orm.where(*condition_list)
        if desc:
            data_orm = data_orm.order_by(cls.id.desc())
        data_orm = data_orm.limit(page_size).offset((page_num - 1) * page_size)

        async with db.conn() as session:
            total = (await session.execute(total_orm)).scalar()
            res = (await session.execute(data_orm)).scalars()
            if columns is None:
                data = [i.to_dict() for i in res]
            else:
                data = [i.serialize(columns=columns) for i in res]

        if total % page_size == 0:
            total_page = total // page_size
        else:
            total_page = total // page_size + 1

        return dict(
            data=data,
            page_num=page_num,
            page_size=page_size,
            total=total,
            total_page=total_page
        )
