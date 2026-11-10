from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class Step(Model):
    type: Literal["send", "wait", "click", "delay"]
    text: str = Field(default="", max_length=4096)
    seconds: int = Field(default=60, ge=1, le=600)

    @model_validator(mode="after")
    def check_text(self):
        if self.type in ("send", "click") and not self.text.strip():
            raise ValueError("发送消息和按钮步骤必须填写内容")
        if self.type == "click" and len(self.text) > 200:
            raise ValueError("按钮文字过长")
        return self


class TaskInput(Model):
    name: str = Field(min_length=1, max_length=60)
    accountId: str = Field(default="", max_length=100)
    kind: Literal["message", "buttons"] = "message"
    target: str = Field(min_length=1, max_length=100)
    targetName: str = Field(default="", max_length=200)
    targetType: Literal["bot", "user", "group", "channel", "self"] = "bot"
    steps: list[Step] = Field(min_length=1, max_length=30)
    schedule: Literal["daily", "weekly", "interval", "once", "cron"] = "daily"
    time: str = "08:30"
    timezone: str = "Asia/Shanghai"
    weekdays: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5], max_length=7)
    interval: int = Field(default=24, ge=1, le=720)
    once: str = ""
    cron: str = Field(default="30 8 * * *", max_length=100)
    jitter: int = Field(default=0, ge=0, le=120)
    notify: Literal["failure", "summary", "all", "none"] = "failure"
    successWords: str = Field(default="", max_length=500)
    failureWords: str = Field(default="", max_length=500)
    enabled: bool = True
    revision: int | None = None

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("请填写任务名称")
        return value.strip()

    @field_validator("target")
    @classmethod
    def target_value(cls, value):
        value = value.strip()
        if not re.fullmatch(r"(?:@[a-zA-Z0-9_]{4,32}|-?\d{1,20}|me)", value):
            raise ValueError("目标应为 @用户名、数字会话 ID 或 me")
        return value

    @field_validator("timezone")
    @classmethod
    def timezone_value(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("时区无效") from None
        return value

    @model_validator(mode="after")
    def validate_flow(self):
        if self.steps[0].type != "send":
            raise ValueError("第一步需要发送消息")
        for i, step in enumerate(self.steps):
            previous = next((s.type for s in reversed(self.steps[:i]) if s.type != "delay"), None)
            if step.type == "click" and previous != "wait":
                raise ValueError("点击按钮前需要等待回复")
        if sum(s.seconds for s in self.steps if s.type in ("wait", "delay")) > 1800:
            raise ValueError("单次任务的等待时间总和不能超过 30 分钟")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", self.time):
            raise ValueError("时间应为 HH:mm 格式")
        if any(day < 0 or day > 6 for day in self.weekdays) or len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("星期范围应为 0 到 6，且不能重复")
        if self.schedule == "weekly" and not self.weekdays:
            raise ValueError("请至少选择一天")
        if self.schedule == "cron" and (len(self.cron.split()) != 5 or not croniter.is_valid(self.cron)):
            raise ValueError("请输入有效的五字段 Cron")
        if self.schedule == "once":
            try:
                datetime.fromisoformat(self.once)
            except ValueError:
                raise ValueError("请填写有效的单次执行日期") from None
        return self


class SettingsInput(Model):
    workspace: str = Field(default="我的工作空间", min_length=1, max_length=30)
    timezone: str = "Asia/Shanghai"
    language: Literal["zh-CN"] = "zh-CN"
    proxyType: Literal["none", "socks5", "http"] = "none"
    proxyHost: str = Field(default="", max_length=253)
    proxyPort: str = "7890"
    notification: Literal["failure", "summary", "all", "none"] = "failure"
    summaryTime: str = "21:00"
    retention: Literal["7", "30", "90"] = "30"
    notifyTarget: Literal["me", "bot"] = "me"
    notifyChat: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def valid(self):
        TaskInput.timezone_value(self.timezone)
        self.workspace = self.workspace.strip()
        if not self.workspace:
            raise ValueError("请填写工作空间名称")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", self.summaryTime):
            raise ValueError("摘要时间无效")
        if self.proxyType != "none":
            if not self.proxyHost.strip() or any(c in self.proxyHost for c in "/@\r\n"):
                raise ValueError("请填写有效的代理主机名或 IP")
            if not self.proxyPort.isdigit() or not 1 <= int(self.proxyPort) <= 65535:
                raise ValueError("代理端口应为 1 到 65535")
        return self


class LoginInput(Model):
    password: str = Field(min_length=1, max_length=1024)


class ApiCredentials(Model):
    apiId: int = Field(gt=0)
    apiHash: str = Field(pattern=r"^[a-fA-F0-9]{32}$")


class PhoneLogin(Model):
    name: str = Field(min_length=1, max_length=30)
    phone: str = Field(pattern=r"^\+[1-9][0-9 ]{6,20}$")
    accountId: str | None = None


class LoginCode(Model):
    code: str = Field(pattern=r"^\d{4,8}$")


class QRStart(Model):
    name: str = Field(min_length=1, max_length=30)
    accountId: str | None = None


class PasswordInput(Model):
    password: str = Field(min_length=1, max_length=1024)


class SessionImport(Model):
    name: str = Field(min_length=1, max_length=30)
    session: str = Field(min_length=20, max_length=4096)
    accountId: str | None = None


class PasswordChange(Model):
    current: str = Field(min_length=1, max_length=1024)
    password: str = Field(min_length=10, max_length=1024)
