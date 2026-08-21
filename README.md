# 双动量信号系统

创业板/中证红利双动量轮动策略的实时信号与历史回测工具。

## 策略逻辑

- **相对动量**：比较两指数的 20 天平滑动量，选择更强的一方
- **绝对动量**：胜者动量需超过无风险利率（1.5% 年化），否则空仓
- **冷却期**：信号切换后 12 天内不允许再次切换（防频繁交易）
- **波动率目标**：根据实现波动率动态调整仓位（目标 14% 年化波动率）

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 部署到 Streamlit Cloud

1. Fork 本仓库到你的 GitHub
2. 访问 [share.streamlit.io](https://share.streamlit.io)
3. 点击 "Deploy an app"
4. 选择仓库 `gongshou`，分支 `master`，主文件 `app.py`
5. 点击 "Deploy"

## 历史表现（2016-2026）

| 指标 | 数值 |
|------|------|
| 年化收益 | 9.80% |
| 最大回撤 | 17.48% |
| 夏普比率 | 0.71 |
| Calmar | 0.56 |

## 技术栈

- Python 3.10+
- Streamlit
- akshare（数据源）
- pandas / numpy
- plotly（可视化）

## 项目结构

```
app.py          # Streamlit 主入口
config.py       # 策略参数配置
data_loader.py  # 数据加载与缓存
strategy.py     # 信号生成逻辑
backtester.py   # 历史回测引擎
tests/          # 单元测试
```

## 注意事项

- 数据来自公开 API（新浪、中证指数），可能存在延迟或缺失
- 本工具仅供研究参考，不构成投资建议
- 冷却期状态在 Streamlit Cloud 上为会话级别（重启后重置）
