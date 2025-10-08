from typing import Any, Callable, Dict, List, Optional, Tuple
import logging
import json
import asyncio
from datetime import datetime

# 导入本地的 croniter 实现
from .croniter import croniter, CroniterError

from fastapi import APIRouter, HTTPException

from notifyhub.plugins.utils import get_plugin_config
from notifyhub.plugins.common import after_setup
from notifyhub.controller.server import server
from notifyhub.controller.schedule import register_cron_job


PLUGIN_ID = "pill_reminder"


pill_reminder_router = APIRouter(prefix=f"/{PLUGIN_ID}", tags=[PLUGIN_ID])

logger = logging.getLogger(__name__)


@pill_reminder_router.get("/ping")
async def ping() -> Dict[str, Any]:
    return {"ok": True, "plugin": PLUGIN_ID}


def _get_config() -> Dict[str, Any]:
    return get_plugin_config(PLUGIN_ID) or {}


def _parse_daily_times(times_str: str) -> List[Tuple[int, int]]:
    """解析每日时间格式：08:00, 12:30, 20:45"""
    result: List[Tuple[int, int]] = []
    for part in (times_str or "").split(","):
        p = part.strip()
        if not p:
            continue
        if ":" not in p:
            continue
        h_str, m_str = p.split(":", 1)
        try:
            h = int(h_str)
            m = int(m_str)
            if 0 <= h <= 23 and 0 <= m <= 59:
                result.append((h, m))
        except Exception:
            continue
    # de-duplicate and sort
    result = sorted(list({(h, m) for h, m in result}))
    return result


_WEEKDAY_MAP: Dict[str, int] = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


def _parse_weekly(weekly_str: str) -> List[Tuple[int, int, int]]:
    # returns list of (weekday, hour, minute)
    results: List[Tuple[int, int, int]] = []
    for part in (weekly_str or "").split(","):
        p = part.strip()
        if not p:
            continue
        # expected "Mon 08:00"
        items = p.split()
        if len(items) != 2 or ":" not in items[1]:
            continue
        wd_raw, hm = items
        wd = _WEEKDAY_MAP.get(wd_raw.lower())
        if wd is None:
            continue
        hs, ms = hm.split(":", 1)
        try:
            h = int(hs); m = int(ms)
            if 0 <= h <= 23 and 0 <= m <= 59:
                results.append((wd, h, m))
        except Exception:
            continue
    # dedupe
    results = sorted(list({(wd, h, m) for wd, h, m in results}))
    return results


def _parse_monthly(monthly_str: str) -> List[Tuple[int, int, int]]:
    # returns list of (day_of_month, hour, minute)
    results: List[Tuple[int, int, int]] = []
    for part in (monthly_str or "").split(","):
        p = part.strip()
        if not p:
            continue
        # expected "15 09:00"
        items = p.split()
        if len(items) != 2 or ":" not in items[1]:
            continue
        try:
            day = int(items[0])
            hs, ms = items[1].split(":", 1)
            h = int(hs); m = int(ms)
            if 1 <= day <= 31 and 0 <= h <= 23 and 0 <= m <= 59:
                results.append((day, h, m))
        except Exception:
            continue
    results = sorted(list({(d, h, m) for d, h, m in results}))
    return results


def _parse_yearly(yearly_str: str) -> List[Tuple[int, int, int, int]]:
    # returns list of (month, day, hour, minute)
    results: List[Tuple[int, int, int, int]] = []
    for part in (yearly_str or "").split(","):
        p = part.strip()
        if not p:
            continue
        # expected "05-01 10:00"
        items = p.split()
        if len(items) != 2 or ":" not in items[1] or "-" not in items[0]:
            continue
        try:
            month_s, day_s = items[0].split("-", 1)
            hs, ms = items[1].split(":", 1)
            month = int(month_s); day = int(day_s); h = int(hs); m = int(ms)
            if 1 <= month <= 12 and 1 <= day <= 31 and 0 <= h <= 23 and 0 <= m <= 59:
                results.append((month, day, h, m))
        except Exception:
            continue
    results = sorted(list({(mo, d, h, m) for mo, d, h, m in results}))
    return results


def _parse_cron_expressions(cron_str: str) -> List[str]:
    """解析 Cron 表达式列表"""
    expressions = []
    for expr in (cron_str or "").split(","):
        expr = expr.strip()
        if expr:
            try:
                # 验证 cron 表达式格式
                croniter.croniter(expr)
                expressions.append(expr)
            except Exception:
                logger.warning("Invalid cron expression: %s", expr)
                continue
    return expressions


def _parse_medicine_list(medicines_str: str) -> List[Dict[str, str]]:
    """解析药品清单文本格式"""
    medicines = []
    if not medicines_str:
        return medicines
    
    for line in medicines_str.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # 解析同一行中的多个药品（用空格分隔，但需要智能识别）
        # 先尝试按行分割，如果一行包含多个药品，再进一步处理
        medicine_entries = _split_medicine_line(line)
        
        for medicine_text in medicine_entries:
            medicine_text = medicine_text.strip()
            if not medicine_text:
                continue
            
            # 解析格式：药品名称 - 用量 [图片URL]
            image_url = ""
            
            # 检查是否有图片URL（用方括号包围）
            if '[' in medicine_text and ']' in medicine_text:
                # 提取图片URL
                start_bracket = medicine_text.rfind('[')
                end_bracket = medicine_text.rfind(']')
                if start_bracket < end_bracket:
                    image_url = medicine_text[start_bracket + 1:end_bracket].strip()
                    medicine_text = medicine_text[:start_bracket].strip()
            
            # 解析药品名称和用量
            if ' - ' in medicine_text:
                name, dosage = medicine_text.split(' - ', 1)
                name = name.strip()
                dosage = dosage.strip()
                if name:
                    medicines.append({
                        "name": name,
                        "dosage": dosage or "1片",
                        "image_url": image_url
                    })
            else:
                # 如果没有分隔符，将整行作为药品名称
                name = medicine_text.strip()
                if name:
                    medicines.append({
                        "name": name,
                        "dosage": "1片",
                        "image_url": image_url
                    })
    
    return medicines


def _split_medicine_line(line: str) -> List[str]:
    """智能分割一行中的多个药品"""
    # 如果行中包含多个药品，尝试智能分割
    # 规则：以"【"开头且包含"】"的药品名称作为分割点
    
    medicines = []
    current_medicine = ""
    
    # 按"【"分割，但保留分割符
    parts = line.split('【')
    
    for i, part in enumerate(parts):
        if i == 0:
            # 第一部分可能不包含药品名称
            if part.strip():
                current_medicine = part.strip()
        else:
            # 从"【"开始的部分
            medicine_text = '【' + part
            
            if current_medicine:
                # 如果当前药品不为空，先保存它
                medicines.append(current_medicine)
            
            # 检查是否包含完整的药品信息（有"】"和" - "）
            if '】' in medicine_text and ' - ' in medicine_text:
                # 找到药品的结束位置
                end_pos = medicine_text.find('】')
                if end_pos != -1:
                    # 查找用量和图片信息
                    remaining = medicine_text[end_pos + 1:]
                    
                    # 查找下一个药品的开始位置（下一个"【"）
                    next_medicine_pos = remaining.find('【')
                    
                    if next_medicine_pos != -1:
                        # 有下一个药品
                        current_medicine = medicine_text[:end_pos + 1] + remaining[:next_medicine_pos]
                        medicines.append(current_medicine.strip())
                        current_medicine = remaining[next_medicine_pos:]
                    else:
                        # 这是最后一个药品
                        current_medicine = medicine_text
                else:
                    current_medicine = medicine_text
            else:
                current_medicine = medicine_text
    
    # 添加最后一个药品
    if current_medicine:
        medicines.append(current_medicine.strip())
    
    # 如果没有找到"【"分割符，返回原始行
    if not medicines:
        medicines = [line]
    
    return medicines


def _parse_medicine_groups_from_config(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """从新的配置格式解析药品分组"""
    groups = {}
    
    # 定义时间段配置
    time_periods = [
        ("medicine_time_1", "medicine_name_1", "medicine_1_", 10),  # 用药时间1最多10个药品
        ("medicine_time_2", "medicine_name_2", "medicine_2_", 10),  # 用药时间2最多10个药品
        ("medicine_time_3", "medicine_name_3", "medicine_3_", 10),  # 用药时间3最多10个药品
        ("medicine_time_4", "medicine_name_4", "medicine_4_", 10),  # 用药时间4最多10个药品
        ("medicine_time_5", "medicine_name_5", "medicine_5_", 10),  # 用药时间5最多10个药品
        ("medicine_time_6", "medicine_name_6", "medicine_6_", 10),  # 用药时间6最多10个药品
        ("medicine_time_7", "medicine_name_7", "medicine_7_", 10),  # 用药时间7最多10个药品
        ("medicine_time_8", "medicine_name_8", "medicine_8_", 10),  # 用药时间8最多10个药品
        ("medicine_time_9", "medicine_name_9", "medicine_9_", 10),  # 用药时间9最多10个药品
        ("medicine_time_10", "medicine_name_10", "medicine_10_", 10)  # 用药时间10最多10个药品
    ]
    
    for time_key, name_key, medicine_prefix, max_medicines in time_periods:
        time_str = config.get(time_key, "").strip()
        if not time_str:
            continue
            
        # 验证时间格式
        if ":" not in time_str:
            continue
        
        try:
            h_str, m_str = time_str.split(":", 1)
            h = int(h_str)
            m = int(m_str)
            if not (0 <= h <= 23 and 0 <= m <= 59):
                continue
        except Exception:
            continue
        
        # 获取自定义名称，如果没有则使用默认名称
        custom_name = config.get(name_key, "").strip()
        if not custom_name:
            # 根据时间段生成默认名称
            if time_key == "medicine_time_1":
                custom_name = "用药时间1"
            elif time_key == "medicine_time_2":
                custom_name = "用药时间2"
            elif time_key == "medicine_time_3":
                custom_name = "用药时间3"
            elif time_key == "medicine_time_4":
                custom_name = "用药时间4"
            elif time_key == "medicine_time_5":
                custom_name = "用药时间5"
            elif time_key == "medicine_time_6":
                custom_name = "用药时间6"
            elif time_key == "medicine_time_7":
                custom_name = "用药时间7"
            elif time_key == "medicine_time_8":
                custom_name = "用药时间8"
            elif time_key == "medicine_time_9":
                custom_name = "用药时间9"
            elif time_key == "medicine_time_10":
                custom_name = "用药时间10"
        
        # 收集该时间段的所有药品
        medicines = []
        for i in range(1, max_medicines + 1):
            medicine_key = f"{medicine_prefix}{i}"
            medicine_str = config.get(medicine_key, "").strip()
            
            if medicine_str:
                # 解析单个药品
                medicine = _parse_single_medicine(medicine_str)
                if medicine:
                    medicines.append(medicine)
        
        if medicines:
            groups[custom_name] = {
                "time": time_str,
                "medicines": medicines
            }
    
    return groups


def _parse_single_medicine(medicine_str: str) -> Optional[Dict[str, str]]:
    """解析单个药品字符串"""
    if not medicine_str:
        return None
    
    # 解析格式：药品名称 - 用量 [图片URL] [渠道名称]
    image_url = ""
    channel = ""
    
    # 检查是否有渠道名称（最后一个方括号）
    if '[' in medicine_str and ']' in medicine_str:
        # 找到最后一个方括号对
        last_bracket_start = medicine_str.rfind('[')
        last_bracket_end = medicine_str.rfind(']')
        
        if last_bracket_start < last_bracket_end:
            # 提取最后一个方括号的内容
            last_content = medicine_str[last_bracket_start + 1:last_bracket_end].strip()
            
            # 检查是否是渠道名称（不包含http://或https://）
            if not last_content.startswith(('http://', 'https://')):
                channel = last_content
                medicine_str = medicine_str[:last_bracket_start].strip()
    
    # 检查是否有图片URL（剩余的方括号）
    if '[' in medicine_str and ']' in medicine_str:
        # 提取图片URL
        start_bracket = medicine_str.rfind('[')
        end_bracket = medicine_str.rfind(']')
        if start_bracket < end_bracket:
            image_url = medicine_str[start_bracket + 1:end_bracket].strip()
            medicine_str = medicine_str[:start_bracket].strip()
    
    # 解析药品名称和用量
    if ' - ' in medicine_str:
        name, dosage = medicine_str.split(' - ', 1)
        name = name.strip()
        dosage = dosage.strip()
        if name:
            return {
                "name": name,
                "dosage": dosage or "1片",
                "image_url": image_url,
                "channel": channel
            }
    else:
        # 如果没有分隔符，将整行作为药品名称
        name = medicine_str.strip()
        if name:
            return {
                "name": name,
                "dosage": "1片",
                "image_url": image_url,
                "channel": channel
            }
    
    return None


def _parse_medicine_groups(groups_str: str) -> Dict[str, Dict[str, Any]]:
    """解析药品分组配置（兼容旧格式）"""
    if not groups_str:
        return {}
    
    try:
        groups = json.loads(groups_str)
        if not isinstance(groups, dict):
            return {}
        
        # 验证和清理数据
        cleaned_groups = {}
        for group_name, group_data in groups.items():
            if not isinstance(group_data, dict):
                continue
            
            time_str = group_data.get("time", "")
            medicines = group_data.get("medicines", [])
            
            if not time_str or not isinstance(medicines, list):
                continue
            
            # 验证时间格式
            if ":" not in time_str:
                continue
            
            try:
                h_str, m_str = time_str.split(":", 1)
                h = int(h_str)
                m = int(m_str)
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    continue
            except Exception:
                continue
            
            # 验证药品数据
            valid_medicines = []
            for medicine in medicines:
                if not isinstance(medicine, dict):
                    continue
                name = medicine.get("name", "").strip()
                dosage = medicine.get("dosage", "").strip()
                if name:
                    valid_medicines.append({
                        "name": name,
                        "dosage": dosage or "1片",
                        "image_url": medicine.get("image_url", "").strip()
                    })
            
            if valid_medicines:
                cleaned_groups[group_name] = {
                    "time": time_str,
                    "medicines": valid_medicines
                }
        
        return cleaned_groups
    except Exception as e:
        logger.error("Failed to parse medicine groups: %s", e)
        return {}


def _check_cron_match(cron_expr: str, now: datetime) -> bool:
    """检查当前时间是否匹配 cron 表达式"""
    try:
        cron = croniter.croniter(cron_expr, now)
        # 获取下一个执行时间
        next_time = cron.get_next(datetime)
        # 如果下一个执行时间在当前时间的前一分钟内，说明匹配
        return (next_time - now).total_seconds() < 60
    except Exception:
        return False


def _send_reminder(title_prefix: str, medicine_name: str, dosage: str, image_url: Optional[str], target_type: str, route_id: Optional[str], channel_name: Optional[str]) -> None:
    title = f"{title_prefix} {medicine_name}"
    content = f"请按时用药：{medicine_name}\n用药量：{dosage}"

    if target_type == "router":
        if not route_id:
            raise HTTPException(status_code=400, detail="route not configured")
        server.send_notify_by_router(route_id=route_id, title=title, content=content, push_img_url=image_url, push_link_url=None)
    elif target_type == "channel":
        if not channel_name:
            raise HTTPException(status_code=400, detail="channel not configured")
        server.send_notify_by_channel(channel_name=channel_name, title=title, content=content, push_img_url=image_url, push_link_url=None)
    else:
        raise HTTPException(status_code=400, detail="invalid target type")
    logger.info("pill_reminder sent: title=%s target=%s route=%s channel=%s", title, target_type, route_id, channel_name)


async def _send_medicine_group_reminder(title_prefix: str, group_name: str, medicines: List[Dict[str, Any]], target_type: str, route_id: Optional[str], channel_name: Optional[str]) -> None:
    """发送药品分组提醒"""
    title = f"{title_prefix} {group_name}"
    
    # 第一条消息：发送药品清单
    content_parts = [f"📋 {group_name}清单："]
    image_urls = []
    
    for i, medicine in enumerate(medicines, 1):
        name = medicine.get("name", "")
        dosage = medicine.get("dosage", "1片")
        img_url = medicine.get("image_url", "").strip()
        
        # 构建药品信息行
        medicine_line = f"{i}. {name} - {dosage}"
        if img_url:
            medicine_line += f" 🖼️"
            image_urls.append(img_url)
        
        content_parts.append(medicine_line)
    
    content = "\n".join(content_parts)
    
    # 确定清单消息的发送渠道：优先使用第一个药品的渠道，否则使用默认渠道
    list_channel = channel_name  # 默认渠道
    if medicines:
        first_medicine_channel = medicines[0].get("channel", "").strip()
        if first_medicine_channel:
            list_channel = first_medicine_channel
        else:
            list_channel = channel_name  # 如果第一个药品没有指定渠道，使用默认渠道
    
    # 发送第一条消息（清单）
    if target_type == "channel":
        if not list_channel:
            raise HTTPException(status_code=400, detail="channel not configured")
        server.send_notify_by_channel(channel_name=list_channel, title=title, content=content, push_img_url=None, push_link_url=None)
    else:
        raise HTTPException(status_code=400, detail="invalid target type")
    
    logger.info("pill_reminder group list sent: title=%s medicines_count=%d target=%s channel=%s", title, len(medicines), target_type, list_channel)
    
    # 等待30秒
    await asyncio.sleep(30)
    
    # 后续消息：每个药品单独发送一条消息
    for i, medicine in enumerate(medicines, 1):
        name = medicine.get("name", "")
        dosage = medicine.get("dosage", "1片")
        img_url = medicine.get("image_url", "").strip()
        medicine_channel = medicine.get("channel", "").strip()
        
        # 如果药品没有指定渠道，使用默认渠道
        if not medicine_channel:
            medicine_channel = channel_name
        
        medicine_title = f"{title_prefix} {group_name} {i}/{len(medicines)}"
        medicine_content = f"💊 {name}\n📏 用量：{dosage}"
        
        # 发送单个药品消息
        if target_type == "channel":
            if not medicine_channel:
                raise HTTPException(status_code=400, detail="channel not configured")
            server.send_notify_by_channel(channel_name=medicine_channel, title=medicine_title, content=medicine_content, push_img_url=img_url, push_link_url=None)
        
        logger.info("pill_reminder medicine sent: title=%s medicine=%s channel=%s", medicine_title, name, medicine_channel)


def _build_task(h: int, m: int) -> Callable[[], None]:
    def task() -> None:
        import asyncio
        config = _get_config()
        target_type: str = (config.get("send_target_type") or "router").strip()
        route_id: Optional[str] = config.get("bind_router")
        channel_name: Optional[str] = config.get("bind_channel")
        title_prefix: str = config.get("title_prefix") or "[用药提醒]"
        medicine_name: str = config.get("medicine_name") or "日常用药"
        dosage: str = config.get("dosage") or "1片"
        image_url: Optional[str] = config.get("image_url") or None
        _send_reminder(title_prefix, medicine_name, dosage, image_url, target_type, route_id, channel_name)
    return task


@after_setup(plugin_id=PLUGIN_ID, desc="注册每日用药提醒定时任务")
def setup_cron_jobs() -> None:
    config = _get_config()
    # 纯 guard：仅注册每分钟守护任务，动态读取配置并决定是否发送
    register_cron_job("*/1 * * * *", "pill_reminder@guard_tick", _guard_tick)


# in-memory guard to avoid duplicate sends within the same day
_last_sent_date: Optional[str] = None
_sent_times_today: set[str] = set()


def _guard_tick() -> None:
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    hour_minute = f"{now.hour:02d}:{now.minute:02d}"

    global _last_sent_date, _sent_times_today
    if _last_sent_date != current_date:
        _last_sent_date = current_date
        _sent_times_today = set()

    config = _get_config()
    schedule_type = config.get("reminder_schedule_type", "daily")
    
    should_send = False
    
    # 优先检查用药时间段配置
    medicine_groups = _parse_medicine_groups_from_config(config)
    should_send = False
    
    if medicine_groups:
        # 如果配置了用药时间段，检查当前时间是否匹配
        for group_name, group_data in medicine_groups.items():
            group_time = group_data.get("time", "")
            if group_time == hour_minute:
                should_send = True
                break
    else:
        # 如果没有配置用药时间段，使用计划类型配置
        if schedule_type == "daily":
            daily_times = _parse_daily_times(config.get("daily_times") or "")
            times_str = {f"{h:02d}:{m:02d}" for h, m in daily_times}
            should_send = hour_minute in times_str
            
        elif schedule_type == "weekly":
            weekly = _parse_weekly(config.get("weekly_times") or "")
            weekday_now = now.weekday()
            should_send = any((wd == weekday_now and h == now.hour and m == now.minute) for wd, h, m in weekly)
            
        elif schedule_type == "monthly":
            monthly = _parse_monthly(config.get("monthly_times") or "")
            day_now = now.day
            should_send = any((d == day_now and h == now.hour and m == now.minute) for d, h, m in monthly)
            
        elif schedule_type == "yearly":
            yearly = _parse_yearly(config.get("yearly_times") or "")
            month_now = now.month
            day_now = now.day
            should_send = any((mo == month_now and d == day_now and h == now.hour and m == now.minute) for mo, d, h, m in yearly)
            
        elif schedule_type == "cron":
            cron_expressions = _parse_cron_expressions(config.get("cron_expressions") or "")
            should_send = any(_check_cron_match(expr, now) for expr in cron_expressions)

    if should_send and hour_minute not in _sent_times_today:
        try:
            target_type: str = "channel"  # 固定使用渠道发送
            default_channel: Optional[str] = config.get("default_channel")
            title_prefix: str = config.get("title_prefix") or "[用药提醒]"
            
            # 发送提醒逻辑
            if medicine_groups:
                # 使用药品分组配置，发送匹配时间段的提醒
                for group_name, group_data in medicine_groups.items():
                    group_time = group_data.get("time", "")
                    if group_time == hour_minute:
                        medicines = group_data.get("medicines", [])
                        if medicines:
                            # 使用 asyncio.run 来运行异步函数
                            asyncio.run(_send_medicine_group_reminder(title_prefix, group_name, medicines, target_type, None, default_channel))
            else:
                # 如果没有配置用药时间段，尝试使用旧的 JSON 配置
                old_medicine_groups = _parse_medicine_groups(config.get("medicine_groups") or "")
                if old_medicine_groups:
                    for group_name, group_data in old_medicine_groups.items():
                        group_time = group_data.get("time", "")
                        if group_time == hour_minute:
                            medicines = group_data.get("medicines", [])
                            if medicines:
                                # 使用 asyncio.run 来运行异步函数
                                asyncio.run(_send_medicine_group_reminder(title_prefix, group_name, medicines, target_type, None, default_channel))
                else:
                    # 使用传统配置（向后兼容）
                    for idx in (1, 2, 3):
                        name_key = "medicine_name" if idx == 1 else f"medicine_name_{idx}"
                        dosage_key = "dosage" if idx == 1 else f"dosage_{idx}"
                        img_key = "image_url" if idx == 1 else f"image_url_{idx}"
                        medicine_name: str = (config.get(name_key) or ("日常用药" if idx == 1 else "")).strip()
                        if not medicine_name and idx > 1:
                            continue
                        dosage: str = (config.get(dosage_key) or ("1片" if idx == 1 else "")).strip()
                        image_url: Optional[str] = (config.get(img_key) or None)
                        _send_reminder(title_prefix, medicine_name, dosage, image_url, target_type, None, default_channel)
            
            _sent_times_today.add(hour_minute)
        except Exception as e:
            logger.error("pill_reminder guard tick error: %s", e)


@pill_reminder_router.post("/trigger")
async def trigger_now() -> Dict[str, Any]:
    config = _get_config()
    target_type: str = "channel"  # 固定使用渠道发送
    default_channel: Optional[str] = config.get("default_channel")
    title_prefix: str = config.get("title_prefix") or "[用药提醒]"
    
    # 优先使用新的时间段配置
    medicine_groups = _parse_medicine_groups_from_config(config)
    
    # 如果没有新配置，尝试使用旧的 JSON 配置
    if not medicine_groups:
        medicine_groups = _parse_medicine_groups(config.get("medicine_groups") or "")
    
    if medicine_groups:
        # 使用药品分组配置，发送所有分组的提醒
        for group_name, group_data in medicine_groups.items():
            medicines = group_data.get("medicines", [])
            if medicines:
                await _send_medicine_group_reminder(title_prefix, group_name, medicines, target_type, None, default_channel)
    else:
        # 使用传统配置（向后兼容）
        for idx in (1, 2, 3):
            name_key = "medicine_name" if idx == 1 else f"medicine_name_{idx}"
            dosage_key = "dosage" if idx == 1 else f"dosage_{idx}"
            img_key = "image_url" if idx == 1 else f"image_url_{idx}"
            medicine_name: str = (config.get(name_key) or ("日常用药" if idx == 1 else "")).strip()
            if not medicine_name and idx > 1:
                continue
            dosage: str = (config.get(dosage_key) or ("1片" if idx == 1 else "")).strip()
            image_url: Optional[str] = (config.get(img_key) or None)
            _send_reminder(title_prefix, medicine_name, dosage, image_url, target_type, None, default_channel)
    
    return {"ok": True}


@pill_reminder_router.get("/status")
async def status() -> Dict[str, Any]:
    config = _get_config()
    schedule_type = config.get("reminder_schedule_type", "daily")
    default_channel: Optional[str] = config.get("default_channel")
    
    # 检查用药时间段配置
    medicine_groups = _parse_medicine_groups_from_config(config)
    
    result = {
        "ok": True,
        "schedule_type": schedule_type,
        "default_channel": default_channel,
        "last_sent_date": _last_sent_date,
        "sent_times_today": sorted(list(_sent_times_today)),
        "using_medicine_groups": bool(medicine_groups),
    }
    
    # 检查渠道配置
    if not default_channel:
        result["ok"] = False
        result["error"] = "default channel not configured"
        return result
    
    if medicine_groups:
        # 如果配置了用药时间段，显示时间段信息
        result["active_times"] = [group_data["time"] for group_data in medicine_groups.values()]
        result["note"] = "使用用药时间段配置，忽略计划类型设置"
    else:
        # 如果没有配置用药时间段，显示计划类型配置
        result["note"] = "使用计划类型配置"
        
        if schedule_type == "daily":
            daily_times = _parse_daily_times(config.get("daily_times") or "")
            result["times_daily"] = [f"{h:02d}:{m:02d}" for h, m in daily_times]
            
        elif schedule_type == "weekly":
            weekly = _parse_weekly(config.get("weekly_times") or "")
            result["times_weekly"] = [f"{wd}-{h:02d}:{m:02d}" for wd, h, m in weekly]
            
        elif schedule_type == "monthly":
            monthly = _parse_monthly(config.get("monthly_times") or "")
            result["times_monthly"] = [f"{d:02d}-{h:02d}:{m:02d}" for d, h, m in monthly]
            
        elif schedule_type == "yearly":
            yearly = _parse_yearly(config.get("yearly_times") or "")
            result["times_yearly"] = [f"{mo:02d}-{d:02d} {h:02d}:{m:02d}" for mo, d, h, m in yearly]
            
        elif schedule_type == "cron":
            cron_expressions = _parse_cron_expressions(config.get("cron_expressions") or "")
            result["cron_expressions"] = cron_expressions
    
    # 显示药品分组信息
    medicine_groups = _parse_medicine_groups_from_config(config)
    if not medicine_groups:
        medicine_groups = _parse_medicine_groups(config.get("medicine_groups") or "")
    
    if medicine_groups:
        result["medicine_groups"] = {
            group_name: {
                "time": group_data["time"],
                "medicines_count": len(group_data["medicines"]),
                "medicines": [
                    {
                        "name": med["name"], 
                        "dosage": med["dosage"],
                        "channel": med.get("channel", default_channel),
                        "has_image": bool(med.get("image_url"))
                    } 
                    for med in group_data["medicines"]
                ]
            }
            for group_name, group_data in medicine_groups.items()
        }
    
    return result


