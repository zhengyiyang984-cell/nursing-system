# 2F 護理排班系統 V3.0

## 啟動方式

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 已內建規則

- 全職至少 8 天休假
- 郭珍君為兼職，只排 D 班，且剛好 10 天
- 最多連續上班 5 天
- 大夜固定 N → N → off → off
- E 後不可接 D
- D 可以接 N
- Meeting M 算上班，但不算臨床 D/E/N 人力
- R 預排休不可被覆蓋
- 自動嘗試多份班表並選最高分
- 彩色 Excel 匯出

## 檔案說明

- `app.py`：Streamlit 主介面
- `config.py`：所有規則與名單
- `loader.py`：Excel 匯入
- `scheduler.py`：排班核心
- `optimizer.py`：多次排班與評分
- `validator.py`：規則檢查
- `statistics.py`：統計表
- `exporter.py`：Excel 彩色匯出
- `utils.py`：日期與工具函式

## 注意

Excel 格式不需要完全固定，但系統需要能在列中找到護理師姓名與班別代號。
若排班結果仍有提醒，代表在目前人力、預排休與規則限制下，系統無法完全滿足所有條件，需要人工調整人力需求或預排條件。
