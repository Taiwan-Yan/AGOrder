import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import datetime
import uuid

# 設定頁面資訊
st.set_page_config(page_title="AG 快餐系統", layout="wide", page_icon="🍔")

# 定義快取清除函式
def clear_cache():
    st.cache_data.clear()

# 初始化 Google Sheets 連線
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"⚠️ 資料庫連線失敗，請檢查 `.streamlit/secrets.toml` 設定。\n錯誤訊息：{e}")
    st.stop()

# 讀取資料表函式 (加入快取處理)
@st.cache_data(ttl=5)
def load_data(worksheet):
    try:
        df = conn.read(worksheet=worksheet, usecols=list(range(10)))
        return df.dropna(how="all")
    except Exception as e:
        df = conn.read(worksheet=worksheet)
        return df.dropna(how="all")
        
def get_setting(settings_df, key, default_value):
    if settings_df.empty: return default_value
    row = settings_df[settings_df["Key"] == key]
    if not row.empty:
        # 特別處理布林值字串
        val = str(row.iloc[0]["Value"]).strip().lower()
        if val in ["true", "1", "yes"]: return True
        if val in ["false", "0", "no"]: return False
        return row.iloc[0]["Value"]
    return default_value

# 標題
st.title("🍔 AG 快餐系統")

# 系統導航
page = st.sidebar.radio("系統導覽", ["👤 客戶點餐 (Customer View)", "🧾 前台訂單狀態 (Order Status)", "📋 訂單處理 (Order Processing)", "🛡️ 管理者後台 (Admin View)"])

if page == "👤 客戶點餐 (Customer View)":
    st.header("🛒 選單與明細")
    
    # 讀取全局設定
    try:
        settings_df = load_data("Settings")
    except Exception:
        settings_df = pd.DataFrame(columns=["Key", "Value"])
        
    # 設定變數取得
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    query_date_str = str(get_setting(settings_df, "QueryDate", today_str))

    # 檢查是否非今日日期
    if query_date_str != today_str:
        warn_col1, warn_col2 = st.columns([3, 1])
        with warn_col1:
            st.warning(f"⚠️ 注意：目前系統點餐的日期為 **{query_date_str}**，並非今日！")
        with warn_col2:
            if st.button("🔄 切換為今日", key="btn_reset_cust", use_container_width=True):
                try:
                    df_to_save = settings_df.copy()
                    if df_to_save.empty: df_to_save = pd.DataFrame(columns=["Key", "Value"])
                    df_to_save = df_to_save[df_to_save["Key"] != "QueryDate"]
                    df_to_save = pd.concat([df_to_save, pd.DataFrame([{"Key": "QueryDate", "Value": today_str}])], ignore_index=True)
                    conn.update(worksheet="Settings", data=df_to_save)
                    clear_cache()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 更新失敗：{e}")
    
    # 載入產品與訂單資料
    products_df = load_data("Products")
    orders_df = load_data("Orders")
    details_df = load_data("Order_Details")
    if products_df.empty:
        st.warning("目前尚無產品資料。")
        st.stop()
    
    # 過濾已上架產品
    active_products = products_df[products_df["Is_Active"] == 1].reset_index(drop=True)
    if active_products.empty:
        st.info("目前無上架產品。")
        st.stop()
    
    # 初始化購物車
    if "cart" not in st.session_state:
        st.session_state.cart = {}

    # 顯示產品與數量選擇
    cols = st.columns(3)
    for index, row in active_products.iterrows():
        with cols[index % 3]:
            with st.container(border=True):
                st.write(f"### {row['Name']}")
                st.write(f"💰 價格: **${row['Price']}**")
                st.write(f"📦 庫存: {row['Stock']}")
            
                # 數量輸入 (自動帶入舊有選擇)
                default_qty = st.session_state.cart.get(row['Name'], {}).get("qty", 0)
                qty = st.number_input(
                    f"數量", 
                    min_value=0, 
                    max_value=int(row["Stock"]) if not pd.isna(row["Stock"]) else 0, 
                    value=default_qty,
                    step=1, 
                    key=f"qty_{row['ID']}"
                )
            
                # 更新購物車記錄
                st.session_state.cart[row['Name']] = {
                    "qty": qty,
                    "price": row['Price'],
                    "id": row['ID']
                }
        
    st.divider()
        
    # 購物車與結帳區段
    st.subheader("🛍️ 您的購物車")
    cart_items = {k: v for k, v in st.session_state.cart.items() if v["qty"] > 0}

    if not cart_items:
        st.info("您的購物車目前是空的，快去點餐吧！")
    else:
        # 建立購物車 DataFrame 以顯示表格
        cart_display = []
        for name, data in cart_items.items():
            cart_display.append({
                "商品名稱": name,
                "單價": data["price"],
                "數量": data["qty"],
                "小計": data["price"] * data["qty"]
            })
        cart_df = pd.DataFrame(cart_display)
    
        # 顯示購物車
        st.dataframe(cart_df, use_container_width=True, hide_index=True)
    
        # 計算總金額
        total_amount = cart_df["小計"].sum()
    
        # 折扣邏輯 (動態抓取 Discounts 資料表)
        discount_amount = 0
        discount_msg = ""
        try:
            discounts_df = load_data("Discounts")
            if not discounts_df.empty:
                # 確保欄位型態正確，過濾出啟用的折扣
                discounts_df["Threshold"] = pd.to_numeric(discounts_df["Threshold"], errors="coerce").fillna(0)
                discounts_df["DiscountRate"] = pd.to_numeric(discounts_df["DiscountRate"], errors="coerce").fillna(1.0)
                discounts_df["Is_Active"] = pd.to_numeric(discounts_df["Is_Active"], errors="coerce").fillna(0).astype(int)
            
                active_discounts = discounts_df[discounts_df["Is_Active"] == 1]
            
                # 找出符合門檻條件，且打折數最多的規則 (值越小越便宜，如 0.8 是 8 折)
                # 也可以設計為折抵金額，這裡以「折扣比例」示範
                applicable = active_discounts[active_discounts["Threshold"] <= total_amount]
                if not applicable.empty:
                    # 抓取折扣後比例最低(最優惠)的那一筆
                    best_discount = applicable.loc[applicable["DiscountRate"].idxmin()]
                
                    rate = best_discount["DiscountRate"]
                    # 如果 rate = 0.9，代表打 9 折，折扣掉的金額是 total * (1 - 0.9)
                    discount_amount = total_amount * (1.0 - rate)
                    discount_msg = f"{best_discount['Name']} (滿 ${best_discount['Threshold']:,.0f} 享 {rate*10} 折)"
                
        except Exception as e:
            st.warning(f"折扣讀取失敗或尚未設定 Discounts 表格。")
        
        final_amount = total_amount - discount_amount
    
        st.write(f"### **總計金額:** ${total_amount}")
        if discount_amount > 0:
            st.success(f"🎉 套用優惠: {discount_msg} - 折扣 ${discount_amount:,.0f}")
        st.write(f"### **應付金額:** ${final_amount:,.0f}")
    
        # 備註輸入
        remark = st.text_input("📝 訂單備註 (例如：少冰、不要蔥、統編等)：")
    
        if st.button("確認結帳 💳", type="primary", use_container_width=True):
            with st.spinner("訂單處理中..."):
                # 產生訂單ID與時間
                order_id = "ORD-" + str(uuid.uuid4())[:8].upper()
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
                # 取得最新資料
                orders_df = load_data("Orders")
                order_details_df = load_data("Order_Details")
                # 重新讀取一次 Products 以確保庫存為最新
                latest_products = load_data("Products").copy()
            
                # 1. 準備寫入 Orders
                new_order = pd.DataFrame([{
                    "OrderID": order_id,
                    "Timestamp": timestamp,
                    "Total_Amount": float(total_amount),
                    "Discounted_Amount": float(final_amount),
                    "Status": "Pending (待處理)",
                    "Admin_Remark": ""
                }])
                if orders_df.empty:
                    updated_orders = new_order
                else:
                    updated_orders = pd.concat([orders_df, new_order], ignore_index=True)
            
                # 2. 準備寫入 Order_Details
                new_details = []
                for item_name, item_data in cart_items.items():
                    new_details.append({
                        "OrderID": order_id,
                        "ProductName": item_name,
                        "Quantity": int(item_data["qty"]),
                        "Price": float(item_data["price"]),
                        "Remark": remark
                    })
                new_details_df = pd.DataFrame(new_details)
                if order_details_df.empty:
                    updated_details = new_details_df
                else:
                    updated_details = pd.concat([order_details_df, new_details_df], ignore_index=True)
                
                # 3. 準備回寫庫存
                for item_name, item_data in cart_items.items():
                    # 尋找對應的產品並扣除庫存
                    idx = latest_products[latest_products["Name"] == item_name].index
                    if not idx.empty:
                        latest_products.loc[idx, "Stock"] -= item_data["qty"]
                        
                # 執行寫入
                try:
                    conn.update(worksheet="Orders", data=updated_orders)
                    conn.update(worksheet="Order_Details", data=updated_details)
                    conn.update(worksheet="Products", data=latest_products)
                    
                    # 清除快取以確保資料重新載入
                    clear_cache()
                    
                    # 訂單成功後清空購物車
                    st.session_state.cart = {}
                    
                    st.success(f"✅ 訂單 {order_id} 建立成功！感謝您的訂購。")
                    
                    # 重設頁面狀態
                    from time import sleep
                    sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 結帳發生錯誤，請稍後再試：{e}")

elif page == "🧾 前台訂單狀態 (Order Status)":
    st.header("🧾 訂單即時狀態")
    
    # 讀取全局設定
    try:
        settings_df = load_data("Settings")
    except Exception:
        settings_df = pd.DataFrame(columns=["Key", "Value"])
        
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    query_date_str = str(get_setting(settings_df, "QueryDate", today_str))

    # 檢查是否非今日日期
    if query_date_str != today_str:
        warn_col1, warn_col2 = st.columns([3, 1])
        with warn_col1:
            st.warning(f"⚠️ 注意：目前查詢的訂單日期為 **{query_date_str}**，並非今日！")
        with warn_col2:
            if st.button("🔄 切換為今日", key="btn_reset_status", use_container_width=True):
                try:
                    df_to_save = settings_df.copy()
                    if df_to_save.empty: df_to_save = pd.DataFrame(columns=["Key", "Value"])
                    df_to_save = df_to_save[df_to_save["Key"] != "QueryDate"]
                    df_to_save = pd.concat([df_to_save, pd.DataFrame([{"Key": "QueryDate", "Value": today_str}])], ignore_index=True)
                    conn.update(worksheet="Settings", data=df_to_save)
                    clear_cache()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 更新失敗：{e}")
    show_unfinished = get_setting(settings_df, "ShowUnfinished", True)
    show_finished = get_setting(settings_df, "ShowFinishedNotPicked", True)
    
    orders_df = load_data("Orders")
    details_df = load_data("Order_Details")
    
    tab_titles = []
    if show_unfinished: tab_titles.append("⏳ 未完成明細")
    if show_finished: tab_titles.append("🛍️ 未取貨已完成明細")
    
    if not tab_titles:
        st.info("管理員目前設定不顯示前台明細。")
        st.stop()
        
    status_tabs = st.tabs(tab_titles)
    
    # ==========================
    # 「⏳ 未完成明細」頁籤
    # ==========================
    if show_unfinished:
        idx = tab_titles.index("⏳ 未完成明細")
        with status_tabs[idx]:
            st.subheader(f"⏳ {query_date_str} - 未完成訂單列表")
            if not orders_df.empty:
                # 過濾出該日期，且狀態為 'Pending' 或 'Preparing'
                orders_df["DateOnly"] = pd.to_datetime(orders_df["Timestamp"], errors="coerce").dt.strftime('%Y-%m-%d')
                unfinished_orders = orders_df[(orders_df["DateOnly"] == query_date_str) & (orders_df["Status"].isin(["Pending", "Pending (待處理)", "Preparing", "Preparing (準備中)"]))]
                
                if unfinished_orders.empty:
                    st.info("目前沒有未完成的訂單。")
                else:
                    for _, order in unfinished_orders.iterrows():
                        with st.container(border=True):
                            st.write(f"**訂單編號:** {order['OrderID']} | **時間:** {order['Timestamp']} | **狀態:** `{order['Status']}`")
                            if not details_df.empty:
                                items = details_df[details_df["OrderID"] == order['OrderID']]
                                st.table(items[["ProductName", "Quantity", "Remark"]])
            else:
                st.info("尚無任何訂單資料。")

    # ==========================
    # 「🛍️ 未取貨已完成明細」頁籤
    # ==========================
    if show_finished:
        idx = tab_titles.index("🛍️ 未取貨已完成明細")
        with status_tabs[idx]:
            st.subheader(f"🛍️ {query_date_str} - 可取貨訂單列表")
            if not orders_df.empty:
                orders_df["DateOnly"] = pd.to_datetime(orders_df["Timestamp"], errors="coerce").dt.strftime('%Y-%m-%d')
                # 狀態為 'Ready'
                finished_orders = orders_df[(orders_df["DateOnly"] == query_date_str) & (orders_df["Status"].isin(["Ready", "Ready (未取貨已完成 / 可取餐)"]))]
                
                if finished_orders.empty:
                    st.info("目前沒有等待取貨的訂單。")
                else:
                    for _, order in finished_orders.iterrows():
                        with st.container(border=True):
                            st.write(f"**訂單編號:** {order['OrderID']} | **時間:** {order['Timestamp']} | **狀態:** `{order['Status']}`")
                            if not details_df.empty:
                                items = details_df[details_df["OrderID"] == order['OrderID']]
                                st.table(items[["ProductName", "Quantity", "Remark"]])
            else:
                st.info("尚無任何訂單資料。")

elif page == "📋 訂單處理 (Order Processing)":
    st.header("📋 訂單處理控制台")
    
    # 登入驗證邏輯
    if "worker_authenticated" not in st.session_state:
        st.session_state.worker_authenticated = False
        
    if not st.session_state.worker_authenticated:
        st.subheader("🔒 工作人員登入")
        worker_password = st.text_input("請輸入工作人員密碼", type="password", key="worker_pw")
        
        # 嘗試讀取 worker_password (即使它被放在了 connections.gsheets 下)
        try:
            correct_password = st.secrets["worker_password"]
        except KeyError:
            try:
                correct_password = st.secrets["connections"]["gsheets"]["worker_password"]
            except KeyError:
                correct_password = "worker123"
        
        if st.button("登入", key="worker_login_btn"):
            if worker_password == correct_password:
                st.session_state.worker_authenticated = True
                st.success("登入成功！")
                st.rerun()
            else:
                st.error("密碼錯誤，請重新輸入。")
        st.stop() # 阻擋未登入的用戶看見後方內容

    # 登出按鈕
    if st.sidebar.button("登出工作人員"):
        st.session_state.worker_authenticated = False
        st.rerun()
        
    st.write("此頁面提供工作人員查看並處理尚未結案的訂單。")
    
    # 日期區間過濾與顯示已完成設定
    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("查詢開始日期 (Start Date)", value=datetime.date.today() - datetime.timedelta(days=7))
    with col2:
        end_date = st.date_input("查詢結束日期 (End Date)", value=datetime.date.today())
    with col3:
        st.write("") # Layout spacing
        st.write("")
        show_completed = st.checkbox("顯示已隱藏的訂單", help="勾選後可檢視並修改『Completed(取貨付款完成)』或『Invisible(不可見)』的歷史訂單狀態。")
    
    orders_df = load_data("Orders")
    details_df = load_data("Order_Details")
    
    # 確保 Admin_Remark 和 Modification_Log 欄位存在 (避免舊資料表缺少該欄位報錯)
    if not orders_df.empty:
        if "Admin_Remark" not in orders_df.columns: orders_df["Admin_Remark"] = ""
        if "Modification_Log" not in orders_df.columns: orders_df["Modification_Log"] = ""
        
    if not orders_df.empty:
        # 轉換日期以進行過濾
        orders_df["DateOnly"] = pd.to_datetime(orders_df["Timestamp"], errors="coerce").dt.date
        mask = (orders_df["DateOnly"] >= start_date) & (orders_df["DateOnly"] <= end_date)
        filtered_orders = orders_df[mask]
        
        # 過濾掉已經不可見的狀態
        if not show_completed:
            hidden_statuses = ["Completed (取貨付款完成)", "Invisible (不可見)", "Completed"]
            pending_orders = filtered_orders[~filtered_orders["Status"].isin(hidden_statuses)]
        else:
            pending_orders = filtered_orders
        
        if pending_orders.empty:
            st.info("太棒了！在該日期區間內，目前沒有待處理的訂單。")
        else:
            for _, order in pending_orders.iterrows():
                with st.expander(f"📍 訂單: {order['OrderID']} | 🕒 {order['Timestamp']} | 狀態: {order['Status']} | 💰 ${order['Discounted_Amount']}", expanded=True):
                    
                    # 顯示此訂單明細
                    if not details_df.empty:
                        order_items = details_df[details_df["OrderID"] == order["OrderID"]]
                        st.table(order_items[["ProductName", "Quantity", "Price", "Remark"]])
                    else:
                        st.warning("無法讀取訂單明細。")
                        
                    st.divider()
                    
                    # 列印按鈕功能
                    with st.expander("🖨️ 列印此訂單 (Print)", expanded=False):
                        # Constructing HTML specifically for printing
                        print_html = f"""
                        <html>
                            <head>
                                <style>
                                    @media print {{
                                        body {{ font-family: sans-serif; padding: 20px; }}
                                        .ticket {{ width: 300px; margin: 0 auto; border: 1px solid #000; padding: 10px; }}
                                        h2, h3, h4 {{ text-align: center; margin: 5px 0; }}
                                        .items {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                                        .items th, .items td {{ border-bottom: 1px dashed #000; padding: 5px 0; text-align: left; }}
                                        .total {{ margin-top: 10px; font-weight: bold; text-align: right; }}
                                    }}
                                </style>
                            </head>
                            <body>
                                <div class="ticket">
                                    <h2>AG 點餐系統</h1>
                                    <p><strong>單號:</strong> {order['OrderID']}</p>
                                    <p><strong>時間:</strong> {order['Timestamp']}</p>
                                    <hr>
                                    <table class="items">
                                        <tr><th>品名</th><th>量</th><th>單價</th><th>備註</th></tr>
                        """
                        if not details_df.empty:
                            for idx, row in order_items.iterrows():
                                remark_txt = row["Remark"] if not pd.isna(row["Remark"]) else ""
                                print_html += f"<tr><td>{row['ProductName']}</td><td>{row['Quantity']}</td><td>{row['Price']}</td><td>{remark_txt}</td></tr>"
                        
                        print_html += f"""
                                    </table>
                                    <div class="total">總計付款: ${order['Discounted_Amount']}</div>
                                </div>
                                <script>
                                    window.print();
                                </script>
                            </body>
                        </html>
                        """
                        if st.button("🖨️ 發送列印指令", key=f"print_{order['OrderID']}"):
                            st.components.v1.html(print_html, height=0)
                            
                    st.divider()
                    
                    # 顯示修改紀錄
                    mod_log = str(order.get("Modification_Log", ""))
                    if mod_log and mod_log != "nan":
                        st.warning(f"📝 訂單修改紀錄:\n{mod_log}")
                        
                    # 修改狀態與備註表單
                    with st.form(key=f"process_form_{order['OrderID']}"):
                        # 處理進度選項 (中英對照)
                        status_options = [
                            "Pending (待處理)",
                            "Preparing (準備中)",
                            "Ready (未取貨已完成 / 可取餐)",
                            "Completed (取貨付款完成)",
                            "Cancelled (已取消)",
                            "Invisible (不可見)"
                        ]
                        
                        # 容錯處理：如果舊狀態是純英文，則轉換
                        current_status = order["Status"]
                        if current_status == "Pending": current_status = "Pending (待處理)"
                        elif current_status == "Preparing": current_status = "Preparing (準備中)"
                        elif current_status == "Ready": current_status = "Ready (未取貨已完成 / 可取餐)"
                        elif current_status == "Completed": current_status = "Completed (取貨付款完成)"
                        elif current_status == "Cancelled": current_status = "Cancelled (已取消)"
                        
                        if current_status not in status_options: current_status = "Pending (待處理)"
                        idx = status_options.index(current_status)
                        
                        new_status = st.selectbox("處理情況 (Status)", status_options, index=idx)
                        
                        # 管理員/廚房備註
                        current_remark = str(order.get("Admin_Remark", ""))
                        if current_remark == "nan": current_remark = ""
                        new_remark = st.text_input("處理備註 (例如：缺貨通知、特殊處理等)", value=current_remark)
                        
                        # 新增刪除與修改金額功能
                        with st.expander("⚠️ 進階危險操作 (修改金額 / 刪除訂單)", expanded=False):
                            amended_amount = st.number_input("修改訂單總付金額", value=float(order["Discounted_Amount"]), min_value=0.0)
                            delete_order = st.checkbox("刪除此訂單 (勾選後儲存將視同作廢且狀態轉為 Invisible)", value=False)
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            submit = st.form_submit_button("💾 儲存進度與備註", use_container_width=True)
                        with c2:
                            # 快速結案按鈕
                            complete_btn = st.form_submit_button("✅ 快速標記為結案", use_container_width=True)
                            
                        if complete_btn:
                            orders_df.loc[orders_df["OrderID"] == order["OrderID"], "Status"] = "Completed (取貨付款完成)"
                            orders_df.loc[orders_df["OrderID"] == order["OrderID"], "Admin_Remark"] = new_remark
                            # Drop the temporary DateOnly column before saving
                            if "DateOnly" in orders_df.columns: orders_df = orders_df.drop(columns=["DateOnly"])
                            conn.update(worksheet="Orders", data=orders_df)
                            clear_cache()
                            st.success(f"訂單 {order['OrderID']} 已結案！")
                            st.rerun()
                        elif submit:
                            # 處理刪除
                            if delete_order:
                                new_status = "Invisible (不可見)"
                                new_remark = f"[{datetime.datetime.now().strftime('%m-%d %H:%M')}] 管理員刪除訂單"
                                
                            # 處理金額修改日誌
                            log_msg = mod_log
                            if float(amended_amount) != float(order["Discounted_Amount"]):
                                log_msg += f"\n[{datetime.datetime.now().strftime('%m-%d %H:%M')}] 金額自 ${order['Discounted_Amount']} 修改為 ${amended_amount}"
                            
                            orders_df.loc[orders_df["OrderID"] == order["OrderID"], "Status"] = new_status
                            orders_df.loc[orders_df["OrderID"] == order["OrderID"], "Admin_Remark"] = new_remark
                            orders_df.loc[orders_df["OrderID"] == order["OrderID"], "Discounted_Amount"] = float(amended_amount)
                            orders_df.loc[orders_df["OrderID"] == order["OrderID"], "Modification_Log"] = log_msg
                            
                            if "DateOnly" in orders_df.columns: orders_df = orders_df.drop(columns=["DateOnly"])
                            conn.update(worksheet="Orders", data=orders_df)
                            clear_cache()
                            st.success(f"訂單狀態已更新。")
                            st.rerun()
    else:
        st.info("尚無任何訂單資料。")

elif page == "🛡️ 管理者後台 (Admin View)":
    st.header("🎛️ 後台管理系統")
    
    # 登入驗證邏輯
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
        
    if not st.session_state.admin_authenticated:
        st.subheader("🔒 管理者登入")
        admin_password = st.text_input("請輸入管理者密碼", type="password")
        
        # 嘗試讀取 admin_password
        try:
            correct_password = st.secrets["admin_password"]
        except KeyError:
            try:
                correct_password = st.secrets["connections"]["gsheets"]["admin_password"]
            except KeyError:
                correct_password = "admin123"
        
        if st.button("登入"):
            if admin_password == correct_password:
                st.session_state.admin_authenticated = True
                st.success("登入成功！")
                st.rerun()
            else:
                st.error("密碼錯誤，請重新輸入。")
        st.stop() # 阻擋未登入的用戶看見後方內容

    # 登出按鈕
    if st.sidebar.button("登出管理者"):
        st.session_state.admin_authenticated = False
        st.rerun()
        
    # 載入所有資料
    orders_df = load_data("Orders")
    details_df = load_data("Order_Details")
    products_df = load_data("Products")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 進銷存分析", "📦 產品維護", "🏷️ 折扣管理", "⚙️ 系統設定"])
    
    with tab1:
        st.subheader("📊 營收與毛利分析")
        
        # 增加日期區間與分析按鈕
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            start_date = st.date_input("分析開始日期", value=datetime.date.today() - datetime.timedelta(days=7), key="ana_start")
        with col2:
            end_date = st.date_input("分析結束日期", value=datetime.date.today(), key="ana_end")
        with col3:
            st.write("") # Padding
            st.write("")
            analyze_btn = st.button("🚀 開始分析", use_container_width=True, type="primary")
            
        if analyze_btn:
            if not orders_df.empty and not details_df.empty and not products_df.empty:
                # 轉換日期過濾
                orders_df["DateOnly"] = pd.to_datetime(orders_df["Timestamp"], errors="coerce").dt.date
                mask = (orders_df["DateOnly"] >= start_date) & (orders_df["DateOnly"] <= end_date)
                
                # 取出 Completed 的訂單
                completed_orders = orders_df[mask & (orders_df["Status"].isin(["Completed", "Completed (取貨付款完成)"]))].copy()
            
            if not completed_orders.empty:
                # 每日營收分析
                st.write("### 📈 每日營業額")
                completed_orders["Date"] = pd.to_datetime(completed_orders["Timestamp"]).dt.date
                daily_revenue = completed_orders.groupby("Date")["Discounted_Amount"].sum().reset_index()
                
                if not daily_revenue.empty:
                    # 使用 st.bar_chart 呈現
                    chart_data = daily_revenue.set_index("Date")
                    st.bar_chart(chart_data)
                
                # 產品毛利分析
                st.write("### 💰 產品毛利分析")
                # 篩選已完成訂單的明細
                completed_details = details_df[details_df["OrderID"].isin(completed_orders["OrderID"])].copy()
                
                # 關聯 Products 取得 Cost
                merged_df = completed_details.merge(products_df[["Name", "Cost"]], left_on="ProductName", right_on="Name", how="left")
                merged_df["Cost"] = merged_df["Cost"].fillna(0)
                
                # 利潤公式：(Price - Cost) * Quantity
                merged_df["Profit"] = (merged_df["Price"] - merged_df["Cost"]) * merged_df["Quantity"]
                profit_by_product = merged_df.groupby("ProductName")["Profit"].sum().reset_index()
                
                if not profit_by_product.empty:
                    st.bar_chart(profit_by_product.set_index("ProductName"))
                else:
                    st.info("尚無足夠的資料可以計算毛利。")
            else:
                st.info("目前尚無已完成(Completed)的訂單。")
        else:
            st.info("資料表內容不足，無法產生報表。")
            
    with tab2:
        st.subheader("📦 產品與庫存維護")
        
        # 若 Products 無資料，建立一份空的 DataFrame 並給定預設欄位
        if products_df.empty:
            products_df = pd.DataFrame(columns=["ID", "Name", "Price", "Cost", "Stock", "Is_Active"])
            st.info("目前無產品資料，請在下方新增您的第一項產品。")
            
        st.write("您可以在下方表格中直接 **新增、修改或刪除** 產品。滑鼠移到表格最下方可新增列(Row)，點擊最左側勾選列後按 `Delete` 鍵可刪除列。")
        
        # 確保資料型態與 data_editor 匹配
        products_df["ID"] = products_df["ID"].astype(str)
        for col in ["Price", "Cost", "Stock"]:
            products_df[col] = pd.to_numeric(products_df[col], errors="coerce").fillna(0)
        products_df["Is_Active"] = pd.to_numeric(products_df["Is_Active"], errors="coerce").fillna(0).astype(bool)
        
        edited_products = st.data_editor(
            products_df, 
            num_rows="dynamic",
            use_container_width=True,
            key="products_editor",
            column_config={
                "ID": st.column_config.TextColumn(
                    "ID",
                    help="產品唯一編號，例如 P001",
                    required=True,
                ),
                "Name": st.column_config.TextColumn(
                    "產品名稱",
                    required=True,
                ),
                "Price": st.column_config.NumberColumn(
                    "售價 (Price)",
                    min_value=0,
                    required=True,
                ),
                "Cost": st.column_config.NumberColumn(
                    "成本 (Cost)",
                    min_value=0,
                    required=True,
                ),
                "Stock": st.column_config.NumberColumn(
                    "庫存 (Stock)",
                    min_value=0,
                    required=True,
                ),
                "Is_Active": st.column_config.CheckboxColumn(
                    "是否上架 (Is_Active)",
                    help="勾選表示上架",
                    default=True,
                )
            }
        )
        
        if st.button("💾 儲存產品變更", type="primary"):
            # 取出需要儲存的資料
            save_df = edited_products.copy()
            save_df = save_df.dropna(how="all")
            
            # 資料驗證邏輯
            has_error = False
            for idx, row in save_df.iterrows():
                if not str(row["ID"]).strip():
                    st.toast(f"第 {idx + 1} 列錯誤：ID 不能為空！", icon="🚨")
                    has_error = True
                if not str(row["Name"]).strip():
                    st.toast(f"第 {idx + 1} 列錯誤：產品名稱不能為空！", icon="🚨")
                    has_error = True
                if float(row["Price"]) < 0:
                    st.toast(f"第 {idx + 1} 列錯誤：Price 不能小於 0！", icon="🚨")
                    has_error = True
                if float(row["Cost"]) < 0:
                    st.toast(f"第 {idx + 1} 列錯誤：Cost 不能小於 0！", icon="🚨")
                    has_error = True
                    
            if has_error:
                st.error("❌ 資料驗證失敗，請修正上方提示的錯誤後再儲存。")
            else:
                # 轉換 Is_Active 回 1 或 0 (配合原先的整數設定)
                save_df["Is_Active"] = save_df["Is_Active"].astype(int)
                
                try:
                    conn.update(worksheet="Products", data=save_df)
                    clear_cache()
                    st.success("✅ 產品資料已成功更新回 Google Sheets！")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 更新失敗：{e}")
                
    with tab3:
        st.subheader("🏷️ 滿額折扣規則設定")
        st.write("設定不同的滿額折扣規則。系統結帳時，會自動挑選**符合門檻且最優惠(DiscountRate 最低)**的規則。\n* 例如：DiscountRate 填 `0.9` 代表打 9 折；`0.85` 代表 85 折。")
        
        discounts_df = load_data("Discounts")
        
        # 若無資料，建立預設空 DataFrame
        if discounts_df.empty:
            discounts_df = pd.DataFrame(columns=["ID", "Name", "Threshold", "DiscountRate", "Is_Active"])
            st.info("尚無折扣設定，請在下方新增。")
            
        # 確保資料型態與 data_editor 匹配
        for col in ["Threshold", "DiscountRate"]:
            discounts_df[col] = pd.to_numeric(discounts_df[col], errors="coerce").fillna(0)
        discounts_df["Is_Active"] = pd.to_numeric(discounts_df["Is_Active"], errors="coerce").fillna(0).astype(bool)
            
        edited_discounts = st.data_editor(
            discounts_df,
            num_rows="dynamic",
            use_container_width=True,
            key="discounts_editor",
            column_config={
                "ID": st.column_config.TextColumn(
                    "規則 ID",
                    help="例如 D001",
                    required=True,
                ),
                "Name": st.column_config.TextColumn(
                    "活動名稱",
                    required=True,
                ),
                "Threshold": st.column_config.NumberColumn(
                    "滿額門檻 ($)",
                    help="訂單總金額達到此數字即適用",
                    min_value=0,
                    required=True,
                ),
                "DiscountRate": st.column_config.NumberColumn(
                    "折扣比例 (0~1)",
                    help="0.9 = 9折, 0.85 = 85折",
                    min_value=0.01,
                    max_value=1.0,
                    step=0.05,
                    required=True,
                ),
                "Is_Active": st.column_config.CheckboxColumn(
                    "是否啟用",
                    default=True,
                )
            }
        )
        
        if st.button("💾 儲存折扣規則", type="primary"):
            save_disc = edited_discounts.copy()
            save_disc["Is_Active"] = save_disc["Is_Active"].astype(int)
            save_disc = save_disc.dropna(how="all")
            
            try:
                conn.update(worksheet="Discounts", data=save_disc)
                clear_cache()
                st.success("✅ 折扣規則已更新！")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 更新失敗：{e}\n(請確認您的 Google Sheets 中是否已經新增了 `Discounts` 工作表。)")
                
    with tab4:
        st.subheader("⚙️ 系統設定 (Global Settings)")
        st.write("此處影響客戶點餐頁面 (Customer View) 的顯示。")
        
        try:
            settings_df = load_data("Settings")
        except Exception:
            settings_df = pd.DataFrame(columns=["Key", "Value"])
            
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # 提取現有設定
        curr_query_date = str(get_setting(settings_df, "QueryDate", today_str))
        curr_show_unfinished = get_setting(settings_df, "ShowUnfinished", True)
        curr_show_finished = get_setting(settings_df, "ShowFinishedNotPicked", True)
        
        with st.form("settings_form"):
            # 日期轉轉
            try:
                def_date = datetime.datetime.strptime(curr_query_date, "%Y-%m-%d").date()
            except:
                def_date = datetime.date.today()
                
            new_query_date = st.date_input("客戶端強制過濾日期 (QueryDate)", value=def_date, help="客戶點餐以及查看明細時，只會看到此日期的相關資訊。")
            new_show_unfinished = st.checkbox("顯示「⏳ 未完成明細」頁籤", value=bool(curr_show_unfinished))
            new_show_finished = st.checkbox("顯示「🛍️ 未取貨已完成明細」頁籤", value=bool(curr_show_finished))
            
            if st.form_submit_button("儲存系統設定", type="primary"):
                # 準備寫回的 DataFrame
                new_settings = pd.DataFrame([
                    {"Key": "QueryDate", "Value": str(new_query_date)},
                    {"Key": "ShowUnfinished", "Value": str(new_show_unfinished)},
                    {"Key": "ShowFinishedNotPicked", "Value": str(new_show_finished)}
                ])
                
                try:
                    conn.update(worksheet="Settings", data=new_settings)
                    clear_cache()
                    st.success("✅ 系統設定已成功更新！")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 更新失敗：{e}\n(請確認您的 Google Sheets 中是否已經新增了 `Settings` 工作表。)")
