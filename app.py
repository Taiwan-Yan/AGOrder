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
        st.error(f"讀取 {worksheet} 資料表失敗：{e}")
        return pd.DataFrame()

# 標題
st.title("🍔 AG 快餐系統")

# 側邊欄導覽
page = st.sidebar.radio("系統導覽", ["👤 客戶點餐 (Customer View)", "📋 訂單處理 (Order Processing)", "🛡️ 管理者後台 (Admin View)"])

if page == "👤 客戶點餐 (Customer View)":
    st.header("🛒 選單與點餐")
    
    # 載入產品資料
    products_df = load_data("Products")
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
    
    st.subheader("📝 餐點選單")
    
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
                    "Status": "Pending",
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
    
    orders_df = load_data("Orders")
    details_df = load_data("Order_Details")
    
    # 確保 Admin_Remark 欄位存在 (避免舊資料表缺少該欄位報錯)
    if not orders_df.empty and "Admin_Remark" not in orders_df.columns:
        orders_df["Admin_Remark"] = ""
        
    if not orders_df.empty:
        pending_orders = orders_df[orders_df["Status"] != "Completed"]
        if pending_orders.empty:
            st.info("太棒了！目前沒有待處理的訂單。")
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
                    
                    # 修改狀態與備註表單
                    with st.form(key=f"process_form_{order['OrderID']}"):
                        # 處理進度選項
                        status_options = ["Pending", "Preparing", "Ready", "Completed", "Cancelled"]
                        current_status = order["Status"] if order["Status"] in status_options else "Pending"
                        idx = status_options.index(current_status)
                        
                        new_status = st.selectbox("處理情況 (Status)", status_options, index=idx)
                        
                        # 管理員/廚房備註
                        current_remark = str(order.get("Admin_Remark", ""))
                        if current_remark == "nan": current_remark = ""
                        new_remark = st.text_input("處理備註 (例如：缺貨通知、特殊處理等)", value=current_remark)
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            submit = st.form_submit_button("💾 儲存進度與備註", use_container_width=True)
                        with c2:
                            # 快速結案按鈕
                            complete_btn = st.form_submit_button("✅ 快速標記為結案", use_container_width=True)
                            
                        if complete_btn:
                            orders_df.loc[orders_df["OrderID"] == order["OrderID"], "Status"] = "Completed"
                            orders_df.loc[orders_df["OrderID"] == order["OrderID"], "Admin_Remark"] = new_remark
                            conn.update(worksheet="Orders", data=orders_df)
                            clear_cache()
                            st.success(f"訂單 {order['OrderID']} 已結案！")
                            st.rerun()
                        elif submit:
                            orders_df.loc[orders_df["OrderID"] == order["OrderID"], "Status"] = new_status
                            orders_df.loc[orders_df["OrderID"] == order["OrderID"], "Admin_Remark"] = new_remark
                            conn.update(worksheet="Orders", data=orders_df)
                            clear_cache()
                            st.success(f"訂單狀態已更新為：{new_status}")
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
    
    tab1, tab2, tab3 = st.tabs(["📊 進銷存分析", "📦 產品維護", "🏷️ 折扣管理"])
    
    with tab1:
        st.subheader("📊 營收與毛利分析")
        if not orders_df.empty and not details_df.empty and not products_df.empty:
            # 取出 Completed 的訂單
            completed_orders = orders_df[orders_df["Status"] == "Completed"].copy()
            
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
        
        # 將 Is_Active 欄位強制轉為數字，避免資料型態錯誤
        if not products_df.empty:
             products_df["Is_Active"] = pd.to_numeric(products_df["Is_Active"], errors="coerce").fillna(0).astype(int)
        
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
            # 轉換 Is_Active 回 1 或 0 (配合原先的整數設定)
            save_df = edited_products.copy()
            save_df["Is_Active"] = save_df["Is_Active"].astype(int)
            
            # 清除全空的列，防止使用者新增又取消導致的 NaN Row
            save_df = save_df.dropna(how="all")
            
            try:
                # 若 Google Sheets 連線套件支援覆寫
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
            
        # 型態確保
        if not discounts_df.empty:
            discounts_df["Is_Active"] = pd.to_numeric(discounts_df["Is_Active"], errors="coerce").fillna(0).astype(int)
            
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
