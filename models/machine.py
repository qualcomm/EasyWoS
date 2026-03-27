"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
from models.base import BaseModel
# from sqlalchemy import ForeignKey
# from common.enums import Status_EN
from sqlalchemy import Column, Boolean, Integer, String


class Machine(BaseModel):

    __tablename__ = 'machine'

    name = Column(String, unique=True, nullable=False)
    host = Column(String, nullable=False)
    username = Column(String(128), nullable=False)
    password = Column(String(128), nullable=False)
    port = Column(Integer, nullable=False)
    status = Column(Boolean, nullable=True)
    arch = Column(String(128), nullable=True)
    os_release = Column(String(128), nullable=True)
    kernel_version = Column(String(128), nullable=True)
    description = Column(String, nullable=True)
