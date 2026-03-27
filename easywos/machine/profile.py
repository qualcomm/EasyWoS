"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
from dataclasses import dataclass


@dataclass
class MachineProfile:
    name: str
    host: str
    username: str
    password: str
    description: str
    port: int = 22


@dataclass
class UpdateMachineProfile:
    username: str
    password: str
    os_release: str
    kernel_version: str
    description: str
    port: int = 22
    status: bool = False
