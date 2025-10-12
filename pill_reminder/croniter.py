"""
简化版 croniter 实现
只包含基本的 cron 表达式解析和匹配功能
"""
import re
from datetime import datetime, timedelta
from typing import List, Optional, Union


class CroniterError(Exception):
    """Croniter 异常类"""
    pass


class Croniter:
    """简化版 Cron 表达式解析器"""
    
    def __init__(self, cron_expr: str, start_time: Optional[datetime] = None):
        """
        初始化 Cron 表达式解析器
        
        Args:
            cron_expr: Cron 表达式 (分 时 日 月 周)
            start_time: 开始时间，默认为当前时间
        """
        self.cron_expr = cron_expr.strip()
        self.start_time = start_time or datetime.now()
        
        # 解析 cron 表达式
        self.minutes, self.hours, self.days, self.months, self.weekdays = self._parse_cron()
    
    def _parse_cron(self) -> tuple:
        """解析 cron 表达式"""
        parts = self.cron_expr.split()
        if len(parts) != 5:
            raise CroniterError(f"Invalid cron expression: {self.cron_expr}")
        
        return (
            self._parse_field(parts[0], 0, 59),    # 分钟
            self._parse_field(parts[1], 0, 23),    # 小时
            self._parse_field(parts[2], 1, 31),    # 日
            self._parse_field(parts[3], 1, 12),    # 月
            self._parse_field(parts[4], 0, 6),     # 周 (0=周日)
        )
    
    def _parse_field(self, field: str, min_val: int, max_val: int) -> List[int]:
        """解析单个字段"""
        if field == '*':
            return list(range(min_val, max_val + 1))
        
        values = []
        for part in field.split(','):
            part = part.strip()
            
            # 处理范围 (如 1-5)
            if '-' in part:
                start, end = part.split('-', 1)
                start_val = int(start)
                end_val = int(end)
                if start_val < min_val or end_val > max_val:
                    raise CroniterError(f"Value out of range: {part}")
                values.extend(range(start_val, end_val + 1))
            
            # 处理步长 (如 */5)
            elif '/' in part:
                base, step = part.split('/', 1)
                step_val = int(step)
                if base == '*':
                    base_values = list(range(min_val, max_val + 1))
                else:
                    base_val = int(base)
                    if base_val < min_val or base_val > max_val:
                        raise CroniterError(f"Value out of range: {base}")
                    base_values = [base_val]
                
                values.extend([v for v in base_values if (v - min_val) % step_val == 0])
            
            # 处理单个值
            else:
                val = int(part)
                if val < min_val or val > max_val:
                    raise CroniterError(f"Value out of range: {val}")
                values.append(val)
        
        return sorted(list(set(values)))
    
    def get_next(self, start_time: Optional[datetime] = None) -> datetime:
        """获取下一个执行时间"""
        current = start_time or self.start_time
        
        # 从下一分钟开始查找
        current = current.replace(second=0, microsecond=0) + timedelta(minutes=1)
        
        # 最多查找一年
        max_iterations = 365 * 24 * 60
        iterations = 0
        
        while iterations < max_iterations:
            if self._matches(current):
                return current
            
            current += timedelta(minutes=1)
            iterations += 1
        
        raise CroniterError("No valid time found within one year")
    
    def _matches(self, dt: datetime) -> bool:
        """检查给定时间是否匹配 cron 表达式"""
        return (
            dt.minute in self.minutes and
            dt.hour in self.hours and
            dt.day in self.days and
            dt.month in self.months and
            dt.weekday() in self.weekdays
        )


def croniter(cron_expr: str, start_time: Optional[datetime] = None) -> Croniter:
    """创建 Croniter 实例的便捷函数"""
    return Croniter(cron_expr, start_time)
