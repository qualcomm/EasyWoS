from models.base import BaseModel
# from sqlalchemy import ForeignKey
# from common.enums import Status_EN
from sqlalchemy import Column, String


class Evaluation(BaseModel):

    __tablename__ = 'evaluation'

    name = Column(String, nullable=False)
    host = Column(String, nullable=False)
    arch = Column(String(32), nullable=False)
    target_arch = Column(String(32), nullable=False)
    os_release = Column(String(100))
    target_os_release = Column(String(100))
    status = Column(String(32), default='running', nullable=False)
    detail = Column(String)
    sys_config = Column(String)
