"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
from models.base import BaseModel

from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Column, Boolean, String


class User(BaseModel):
    __tablename__ = 'user'

    username = Column(String(128), unique=True, nullable=False)
    password = Column(String(128), nullable=False)
    status = Column(Boolean, nullable=True)

    def set_password(self, password):
        """encode password"""
        self.password = generate_password_hash(password)

    def check_password(self, password):
        """check whether password is correct"""
        return check_password_hash(self.password, password)
