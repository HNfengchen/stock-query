# Stock Query 项目代码智能体指南

## 构建、测试和 linting

### 测试运行

目前项目尚未建立正式的测试框架。建议的测试方法：

```bash
# 运行特定功能测试
python -m pytest tests/test_specific_feature.py -v

# 运行所有测试
python -m pytest tests/ -v

# 运行单个测试函数
python -m pytest tests/test_specific_feature.py::test_function_name -v
```

> **注意**：由于项目尚未建立测试目录结构，您可能需要先创建 `tests/` 目录并添加适当的测试文件。

### 代码检查 (Linting)

建议使用以下工具进行代码质量检查：

```bash
# 使用 flake8 进行代码风格检查
flake8 scripts/ --max-line-length=88 --extend-ignore=E203,W503

# 使用 black 进行代码格式化
black scripts/ --line-length=88

# 使用 isort 进行导入排序
isort scripts/
```

### 类型检查

```bash
# 使用 mypy 进行类型检查
mypy scripts/ --ignore-missing-imports
```

## 代码风格指南

### 导入约定

1. 标准库导入放在最前面
2. 第三方库导入放在其次
3. 本地项目导入放在最后
4. 使用绝对导入而非相对导入（在本项目中）
5. 导入语句按照字母顺序排序

**正确示例：**
```python
# 标准库导入
import os
import sys
from datetime import datetime
from typing import Dict, Optional, Tuple

# 第三方库导入
import efinance as ef
import pandas as pd
import numpy as np
import yaml

# 本地项目导入
from .technical_indicators import calculate_all_indicators
from .core.data_fetcher import DataFetcher
```

### 代码格式化

1. 使用 4 个空格进行缩进（不使用制表符）
2. 最大行长度为 88 个字符（符合 Black 默认设置）
3. 函数和类之间使用两个空行分隔
4. 方法之间使用一个空行分隔
5. 导入语句块之间使用一个空行分隔

### 类型注解

1. 所有公共函数必须添加类型注解
2. 复杂的返回类型使用 `typing` 模块中的类型
3. 私有函数建议添加类型注解以提高代码可读性

**正确示例：**
```python
def parse_stock_code(user_input: str) -> Tuple[Optional[str], Optional[str]]:
    """
    解析用户输入，返回股票代码和市场标识
    
    参数:
        user_input: 用户输入的股票代码或名称
    
    返回:
        tuple: (stock_code, market) market为'sh'或'sz'
    """
    # 实现代码
```

### 命名约定

1. **函数和变量**：使用 snake_case
2. **类名**：使用 PascalCase
3. **常量**：使用全大写 snake_case
4. **模块名**：使用小写，可以使用下划线分隔
5. **私有方法和变量**：以下划线开头的 snake_case

**示例：**
```python
# 良好的命名
def get_stock_info(stock_code: str) -> Dict:
    MAX_RETRIES = 3
    RETRY_DELAY = 1
    
    class StockAnalyzer:
        def _fetch_data(self) -> pd.DataFrame:
            pass
```

### 错误处理

1. 使用 try/except 块捕获特定异常，避免使用裸露的 except:
2. 在捕获异常后，应该记录错误信息或重新抛出更具体的异常
3. 对于外部服务调用（如API请求），应该实现重试机制
4. 不要在生产代码中使用 print() 进行错误报告，应使用日志系统

**正确示例：**
```python
def get_stock_info(stock_code: str) -> Dict:
    info = {"代码": stock_code}
    
    try:
        # 尝试从xtquant获取数据
        xdata = _get_xtdata()
        if xdata:
            # ... 处理xtquant数据
            pass
    except ImportError:
        # xtquant未安装，继续尝试其他数据源
        pass
    except Exception as e:
        # 记录具体错误但不中断执行
        print(f"xtquant 获取实时行情失败: {e}")
    
    try:
        # 尝试从efinance获取数据
        # ... 处理efinance数据
        pass
    except Exception as e:
        print(f"efinance 获取实时行情失败: {e}")
    
    return info
```

### 注释和文档字符串

1. 所有公共函数和类必须有文档字符串（docstring）
2. 文档字符串应描述函数的目的、参数、返回值和可能的异常
3. 使用三重双引号（"""）进行文档字符串
4. 对于复杂的业务逻辑，添加内联注释解释原因

**文档字符串格式：**
```python
def get_stock_info(stock_code: str) -> Dict:
    """
    获取股票基本信息
    
    参数:
        stock_code: 股票代码
    
    返回:
        dict: 股票基本信息
    """
    # 实现代码
```

### 数据处理

1. 处理 pandas DataFrame 时，检查数据是否为空或None
2. 使用 .get() 方法安全地访问字典值，提供默认值
3. 对于数值计算，注意处理 NaN 和无穷大值
4. 日期时间处理使用 datetime 模块，保持时区一致性

**正确示例：**
```python
def get_stock_info(stock_code: str) -> Dict:
    info = {"代码": stock_code}
    
    # 安全获取数据
    try:
        s = ef.stock.get_quote_snapshot(stock_code)
        if s is not None and not s.empty:
            # 处理数据...
            pass
    except Exception as e:
        print(f"efinance 获取实时行情失败: {e}")
    
    return info
```