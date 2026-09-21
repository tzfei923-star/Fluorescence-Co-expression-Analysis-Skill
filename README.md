# Fluorescence Co-expression Analysis Skill

雙通道螢光共表現 (co-expression / co-localization) 分析工具，以像素等級計算兩個標記（如 SOX2 / GFP）在共軛焦顯微影像中的重疊比例。支援 CZI（Zeiss 原始檔）、TIFF（單通道）與 JPEG（RGB 配對）三種輸入格式。

這是一個 Claude / Claude Code 的 Agent Skill。核心邏輯與流程定義於 SKILL.md。

## 這個 Skill 能做什麼

- 從螢光顯微影像自動抓出兩個 channel 的訊號
- 依訊號分佈自動挑選合適的閾值（Otsu / mean+2SD / 百分位）
- 計算三個關鍵數字：GFP+ 面積、SOX2+ 面積、共表現面積
- 產生主要指標 共表現 / GFP+（所有 GFP 標記細胞中，同時表現 SOX2 的比例）
- 輸出視覺化疊圖（magenta = SOX2、green = GFP、yellow = 共表現）
- 多樣本可依實驗組別統整為 mean ± SD

## 安裝方式

### 方法 A — 放到 Claude Code 的 skills 目錄

\`\`\`bash
# 專案層級
mkdir -p .claude/skills/fluorescence-coexpression
cp SKILL.md .claude/skills/fluorescence-coexpression/

# 或使用者層級
mkdir -p ~/.claude/skills/fluorescence-coexpression
cp SKILL.md ~/.claude/skills/fluorescence-coexpression/
\`\`\`

目錄結構應為：

\`\`\`
fluorescence-coexpression/
└── SKILL.md
\`\`\`

### 方法 B — 從 GitHub clone

\`\`\`bash
git clone https://github.com/<your-username>/fluorescence-coexpression.git
cp -r fluorescence-coexpression ~/.claude/skills/
\`\`\`

安裝後，Claude 會在你上傳螢光影像或提到「算共表現 / co-expression / 兩個 channel 重疊」時自動觸發此 skill。

## 環境需求

Python 3.9+，以及下列套件：

\`\`\`bash
pip install numpy pillow scikit-image
\`\`\`

- numpy — 陣列運算
- pillow — 讀取 TIFF / JPEG
- scikit-image — Otsu 閾值

CZI 為自行解析（不需額外套件），但如有需要可安裝 czifile 或 aicsimageio 作交叉驗證。

## 使用方式

上傳影像後，直接用自然語言請 Claude 分析，例如：

- 幫我算這兩張圖的 SOX2 / GFP 共表現比例
- 這個 CZI 檔裡 GFP+ 的細胞有多少同時是 SOX2+？
- 算共表現，然後把三組樣本做 mean ± SD

## 分析流程

1. 判斷輸入格式（CZI / TIFF / JPEG）
2. 讀取影像資料、取出兩個 channel
3. 依格式與訊號分佈挑選閾值
4. 計算共表現（共表現 = SOX2 mask AND GFP mask）
5. 產生疊圖與 mask 圖
6. 以卡片 + 長條圖呈現結果
7. 多樣本依組別統整

## 通道與顏色對應

| 標記 | 顏色 | RGB channel |
| --- | --- | --- |
| SOX2 | magenta / 紫 | R |
| GFP | green / 綠 | G |
| 共表現 | yellow / 黃 | — |

若通道指定不明確，Claude 會先向你確認。

## 閾值選擇速查

| 情況 | 建議方法 | 原因 |
| --- | --- | --- |
| SOX2（任何格式） | Otsu | 通常呈雙峰（背景 + 訊號） |
| GFP，16-bit CZI | mean + 2SD | 右偏、無明顯雙峰 |
| GFP，8-bit TIFF（ZEN 匯出） | Otsu | 已顯示正規化 |
| GFP，8-bit JPEG（暗背景） | mean + 2SD | 大量零值會扭曲 Otsu |
| 兩通道都很亮（高背景） | p80 百分位 | 兩通道用一致百分位 |

### 閾值可能有誤的警訊

- SOX2+ 或 GFP+ 剛好 = 20% → 可能是被強制套百分位，而非真實訊號
- 共表現 > 80% → 閾值太低，抓進背景重疊
- 共表現 < 0.5% 但肉眼明顯看得到共表現細胞 → 閾值太高

## 重要注意事項（結果解讀）

- 像素面積 ≠ 細胞數：本方法數的是像素，不是單顆細胞。只有在細胞大小相近時，結果才近似細胞層級的共表現。
- JPEG 壓縮：邊界會產生顏色混合，建議優先使用 TIFF 或 CZI。
- MAX projection：堆疊所有 Z 平面會高估共表現；單一平面較保守、較接近真實細胞層級重疊。
- 16-bit CZI 高背景：閾值選擇對結果影響很大，務必記錄使用的方法並在各樣本間一致套用。
- 截斷的 CZI：若偵測到檔案大小不符，會補零並警告；該 channel 的結果不可靠。

## 授權與免責

本工具供研究與教學用途。分析結果為像素等級估計，正式發表前請以細胞計數等方法交叉驗證，並在方法段清楚記錄所用的閾值方法與參數。

## 檔案清單

\`\`\`
.
├── SKILL.md     # Skill 核心定義（流程、程式碼、閾值邏輯）
└── README.md    # 本使用指南
\`\`\`
