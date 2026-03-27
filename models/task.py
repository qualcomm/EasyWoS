"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
from models.base import BaseModel
from sqlalchemy import ForeignKey
# from common.enums import Status_EN
from sqlalchemy import Column, String, Integer, Boolean


class Task(BaseModel):

    __tablename__ = 'task'

    name = Column(String, unique=True, nullable=False)
    userid = Column(Integer, ForeignKey('user.id'), nullable=False)
    file_path = Column(String(128), nullable=False)
    language = Column(String(128), nullable=False)
    locale = Column(String(128), nullable=True)
    repeat_type = Column(String(128), nullable=True)
    arch = Column(String(128), nullable=True)
    build_tool = Column(String(128), nullable=True)
    description = Column(String, nullable=True)
    issue_found = Column(Boolean, nullable=True)


class TaskResult(BaseModel):

    __tablename__ = 'taskresult'

    name = Column(String(128), nullable=True)
    task_id = Column(Integer, ForeignKey('task.id'), nullable=False)
    result_file_path = Column(String(128), nullable=True)
    result_status = Column(String(128), nullable=True)
    log_path = Column(String(128), nullable=True)
    issue_found = Column(Boolean, nullable=True)
