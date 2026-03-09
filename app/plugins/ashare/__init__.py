"""A股行情插件 — 通过新浪财经获取中国 A 股实时数据."""

from app.plugins.defaults import create_plugin
from app.plugins.ashare.provider import AShareProvider

plugin = create_plugin(__file__, AShareProvider)
