# 🍔 AG 快餐系統 - Google Sheets 點餐後台

這是一個使用 Streamlit 搭配 Google Sheets 作為資料庫的輕量化點餐與進銷存管理系統。

## ✨ 系統功能特色

1. **👤 客戶點餐 (Customer View)**
   - 動態顯示已上架菜單及即時庫存。
   - 購物車功能與備註填寫。
   - **動態滿額折扣**：自動抓取建立好的折扣規則，結帳時為客戶套用最划算的折扣。
   - 結帳後即時扣除 Google Sheets 中的庫存。
2. **📋 訂單處理 (Order Processing)**
   - 專門給予備餐人員的控制台（密碼防護）。
   - 可更改訂單進度 (Preparing, Ready 等)。
   - 可獨立新增「管理員備註」欄位。
3. **🛡️ 管理者後台 (Admin View)**
   - 管理者密碼驗證防護。
   - **進銷存分析**：自動分析每日營業額與各產品毛利。
   - **產品維護**：在網頁上直接新增、修改或刪除產品。
   - **折扣管理**：自訂各種滿額打折的規則，隨時啟用或停用。

---

## 🚀 本地端安裝與執行方式

1. **安裝 Python 3.9+**
2. **複製專案並安裝依賴套件：**
   ```bash
   pip install -r requirements.txt
   ```
3. **準備您的 Google Sheets 資料庫**：
   請建立一個全新的試算表，並包含以下五個工作表 (Tabs)：
   - `Products` (欄位: ID, Name, Price, Cost, Stock, Is_Active)
   - `Orders` (欄位: OrderID, Timestamp, Total_Amount, Discounted_Amount, Status, Admin_Remark, Modification_Log)
   - `Order_Details` (欄位: OrderID, ProductName, Quantity, Price, Remark)
   - `Discounts` (欄位: ID, Name, Threshold, DiscountRate, Is_Active)
   - `Settings` (欄位: Key, Value)
4. **設定 Google Sheets 連線 Secrets (很重要！)**
   - 按照下方的「Google Sheets 金鑰設定」，在專案建立 `.streamlit/secrets.toml`。
5. **啟動應用程式：**
   ```bash
   streamlit run app.py
   ```

---

## 📊 Google Sheets 資料表結構參考
為了讓系統正常運作，您的 Google 試算表必須包含以下**五個獨立的工作表 (Tabs)**，並且**第一列(Row 1) 必須填寫完全一致的欄位名稱 (Header)**：

### 1. `Products` (產品清單)
| ID | Name | Price | Cost | Stock | Is_Active |
|:---|:---|:---|:---|:---|:---|
| P001 | 排骨飯 | 100 | 60 | 50 | 1 |
| P002 | 雞腿飯 | 120 | 75 | 30 | 1 |
*(註：Is_Active 中 1 代表上架、0 代表下架)*

### 2. `Orders` (訂單總覽)
| OrderID | Timestamp | Total_Amount | Discounted_Amount | Status | Admin_Remark | Modification_Log |
|:---|:---|:---|:---|:---|:---|:---|
| ORD-A1B2 | 2024-03-01 12:00:00 | 500 | 450 | Pending (待處理) | (管理員備註) | (修改金額與時間紀錄) |

### 3. `Order_Details` (訂單明細)
| OrderID | ProductName | Quantity | Price | Remark |
|:---|:---|:---|:---|:---|
| ORD-A1B2 | 排骨飯 | 2 | 100 | 不要蔥 |

### 4. `Discounts` (折扣規則)
| ID | Name | Threshold | DiscountRate | Is_Active |
|:---|:---|:---|:---|:---|
| D001 | 滿五百九折 | 500 | 0.9 | 1 |
| D002 | 滿千八五折 | 1000 | 0.85 | 1 |

### 5. `Settings` (系統全域設定)
此表用於儲存管理者後台的設定，影響客戶點餐畫面的資料顯示。
| Key | Value |
|:---|:---|
| QueryDate | 2024-12-01 |
| ShowUnfinished | True |
| ShowFinishedNotPicked | False |

---

## 🔑 金鑰設定 (`.streamlit/secrets.toml`)

本專案使用兩組登入密碼以及 Google 服務帳戶連線。請在專案根目錄建立 `.streamlit/secrets.toml` 並填入：

```toml
# ===============================
# 系統介面登入密碼
# ===============================
admin_password = "XXX"      # 管理者後台密碼
worker_password = "XXX"     # 訂單處理頁面密碼

# ===============================
# Google Sheets 資料庫連線
# ===============================
[connections.gsheets]
type = "gsheets"
spreadsheet = "https://docs.google.com/spreadsheets/d/您的試算表ID/edit"

# --- 以下貼上 Google Service Account JSON 的內容，並轉為 TOML 格式 ---
type = "service_account"
project_id = "您的專案ID"
private_key_id = "您的私鑰ID"
private_key = "-----BEGIN PRIVATE KEY-----\n您的私鑰內容(換行必須保留為 \\n)\n-----END PRIVATE KEY-----\n"
client_email = "您的服務帳戶 Email"
client_id = "您的 Client ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "您的 Cert URL"
```
> **注意**：請記得將您的 Google Sheet 分享權限（編輯者）開放給上方 JSON 裡面的 `client_email`。
> **保護金鑰**：此專案已經設定 `.gitignore` 來忽略 `secrets.toml`，以防金鑰外洩。

---

## 🌐 程式碼推送到 GitHub 與部署設定

### 為什麼不能使用 GitHub Pages？
> ⚠️ **重要觀念**：GitHub Pages 僅支援存放**靜態網頁（HTML / CSS / JS）**。
> 因為我們的 AG 快餐系統是使用 **Streamlit（基於 Python 的動態伺服器框架）**開發的，必須要有一個具有 Python 執行環境的伺服器才能運作。因此，**無法直接將此專案發佈在 GitHub Pages 上**。
>
> 不過別擔心！官方有提供另一個免費、一鍵從 GitHub 部署的平台：**Streamlit Community Cloud**。


### 第一步：教您如何把程式碼上傳到 GitHub
請確認您的電腦已經有安裝 [Git](https://git-scm.com/)。開啟終端機 (Terminal / 系統提示字元) 並切換到專案資料夾底下，依序輸入：

1. **初始化 Git 儲存庫並加入檔案**：
   ```bash
   git init
   git add .
   ```
   *(註：我們已經設定好 `.gitignore`，所以 `secrets.toml` 等機密檔案不會被加進去)*

2. **提交 (Commit) 這包程式碼**：
   ```bash
   git commit -m "Initial commit: AG 快餐系統初版"
   ```

3. **連結到您在 GitHub 建立的遠端存放區**：
   請先至 GitHub 網站點擊「New Repository」建立一個全新的 Repo (不要勾選 Add a README file)，取得您的遠端網址後，執行以下指令：
   ```bash
   git branch -M main
   git remote add origin https://github.com/您的帳號/您的Repo名稱.git
   git push -u origin main
   ```
   成功推上去後，您就可以在 GitHub 網站上看到這些檔案了！

---

### 第二步：從 GitHub 部署到 Streamlit Community Cloud (免費)
既然已經將程式碼放在 GitHub 上，接下來我們只要讓 Streamlit 去抓您 GitHub 上的代碼來跑就可以了：

1. **登入並連結**：
   前往 **[Streamlit Community Cloud](https://share.streamlit.io/)** 並使用您的 GitHub 帳號登入。
   
2. **建立新的應用程式 (New App)**：
   - 點擊右上角的 **New app**。
   - 選擇 **Use existing repo**。
   - 在 **Repository** 欄位中，選取您剛剛推上去的 Repo (例如 `您的帳號/ag-food-system`)。
   - **Branch** 選擇 `main`。
   - **Main file path** 請輸入 `app.py`。
   
3. **在雲端貼上 Secrets 金鑰設定**：
   ⚠️ **這步最關鍵！因為我們沒有上傳 `secrets.toml`，雲端主機會拿不到 Google 資料庫權限。**
   - 點擊設定下方的 **「Advanced Settings」**（或是部署成功後的 App settings > **Secrets**）。
   - 請打開您自己在本地端電腦的 `.streamlit/secrets.toml` 檔案，複製裡面所有的文字。
   - 將文字完整貼上雲端畫面的文字框內，並點選 **Save**。

4. **一鍵上線**：
   - 最後點擊 **Deploy!**。
   - 稍等約 1~2 分鐘，待畫面轉圈圈結束並跑完 Python 套件安裝，您的專屬網址就大功告成了！全網都可以連線進入您的點餐系統囉！

> **自動更新 (CI/CD)**: 未來只要您在本地端改好程式碼，並執行 `git push` 把新程式推送到 GitHub，Streamlit 雲端就會偵測到變化，並在一兩分鐘內自動更新您的網頁，完全不需要重新部署！
