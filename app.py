import streamlit as st
import numpy as np
import plotly.graph_objects as go

# ================= 页面配置 =================
st.set_page_config(page_title="湖南园区光储充现货交易风险量化模型", layout="wide")

# 满足要求2：将右侧指标数值字体调小，允许换行，不再显示省略号
st.markdown('''
<style>
div[data-testid="stMetricValue"] {
    font-size: 22px !important;
    white-space: normal !important;
    word-break: break-word !important;
    overflow: visible !important;
    text-overflow: unset !important;
}
</style>
''', unsafe_allow_html=True)

st.title("⚡ 湖南省园区综合能源电价与现货交易风险量化模型 (第四监管周期版 v1.4)")
st.caption("v1.4 升级：适配增量光伏余电上网“二选一”结算方案（竞价机制电价 vs 全现货） ｜ 现货极寒行情校准")
st.markdown("---")

# ================= 侧边栏：园区参数（湖南园区） =================
st.sidebar.header("📊 园区参数设定")

st.sidebar.subheader("1. 物理资产与需量管理")
trans_cap = st.sidebar.slider("变压器容量 (kVA)", 1000, 20000, 8000, 500)
current_demand = st.sidebar.slider("当前月均申报需量 (kW)", 1000, 15000, 5000, 250)
demand_reduction = st.sidebar.slider("需量压降目标 (kW)", 0, 2000, 800, 50)
demand_price = st.sidebar.slider("需量电费单价 (元/kW·月)", 20.0, 60.0, 35.4, 0.5)

# 满足要求1：将左侧年总用电量初始值由4500调整为2500
park_total_elec = st.sidebar.slider("年总用电量 (万kWh/年)", 500, 20000, 2500, 500)

pv_cap = st.sidebar.slider("光伏装机 (MW)", 0.0, 20.0, 6.0, 0.5)
ess_cap = st.sidebar.slider("储能装机 (MWh)", 0.0, 50.0, 15.0, 1.0)
ess_cycle = st.sidebar.slider("储能日循环次数", 0.5, 2.5, 1.9, 0.1)
ev_cap = st.sidebar.slider("充电桩装机 (kW)", 0, 10000, 4000, 500)
pv_deg = st.sidebar.slider("光伏年衰减率 (%)", 0.1, 2.0, 0.5, 0.1)
ess_deg = st.sidebar.slider("储能年衰减率 (%)", 0.5, 5.0, 2.0, 0.5)

st.sidebar.subheader("2. 湖南分时电价参数")
spread_normal = st.sidebar.slider("常态峰谷价差 (元/kWh)", 0.3, 1.2, 0.824, 0.01)
spread_peak = st.sidebar.slider("尖峰峰谷价差 (元/kWh)", 0.5, 1.6, 1.08, 0.01)
price_flat = st.sidebar.slider("平段电价 (元/kWh)", 0.4, 1.0, 0.74, 0.01)
price_valley = st.sidebar.slider("午间低谷电价 (元/kWh)", 0.1, 0.6, 0.33, 0.01)

st.sidebar.subheader("3. 增量光伏余电上网价格模式 (二选一)")
feed_mode = st.sidebar.radio(
    "光伏余电入市结算方案",
    ["竞价成功：80%机制电价 + 20%现货", "未参与竞价：全额现货市场价"],
    help="竞价成功者享受机制电价；未竞价者余电全额按现货结算。"
)
mech_price = st.sidebar.number_input("机制电价 (元/kWh)", value=0.375, step=0.005)
spot_mean = st.sidebar.slider("现货日前均价期望 (元/kWh)", 0.01, 0.55, 0.10, 0.01, help="参考：湖南26年4月、6月现货约0.075元，5月约0.15元")
spot_sigma = st.sidebar.slider("现货价格波动率 (Sigma)", 0.05, 0.30, 0.15, 0.01)

st.sidebar.subheader("4. 偏差考核 (湖南'两个细则'/现货规则)")
deviation_sigma = st.sidebar.slider("光伏预测误差标准差 (%)", 2.0, 20.0, 8.0, 1.0) / 100.0
penalty_multiplier = st.sidebar.slider("偏差惩罚倍数 (实时电价)", 1.0, 3.0, 1.5, 0.1)
deviation_threshold = st.sidebar.slider("免考核死区 (%)", 0.0, 10.0, 3.0, 0.5) / 100.0

st.sidebar.subheader("5. 年化校准与冰冻周压力测试")
annual_factor = st.sidebar.slider("年化折算系数 (汛期弃光/受阻折减)", 0.60, 1.00, 0.80, 0.05)
ice_pv_drop = st.sidebar.slider("冰冻周光伏出力骤降 (%)", 0, 90, 60, 5) / 100.0
ice_price_surge = st.sidebar.slider("冰冻周现货电价飙升 (%)", 0, 150, 60, 5) / 100.0

st.sidebar.markdown("---")
st.sidebar.info("💡 专家提示：依据最新合规推演模型，增量光伏项目余电上网必须严格执行『竞价机制电价』或『全现货市场价』二选一；同时需量电费核定严格恪守 40% 变压器容量底线。")

# ================= 财务与工程常量 =================
PV_HOURS = 1000.0                      
LOAN_RATIO, LOAN_RATE, LOAN_TERM = 0.70, 0.045, 10 
PV_COST, ESS_COST, EV_COST = 280.0, 70.0, 700.0    
EV_HOURS, EV_FEE = 3.0, 0.45           

# ================= 30天小时级现货模拟 =================
def simulate_spot(days=30):
    np.random.seed(42)
    hours = days * 24
    t = np.arange(hours)
    h = t % 24
    daily_cycle = (np.where((h >= 7) & (h <= 9), 0.10, 0) +
                   np.where((h >= 17) & (h <= 22), 0.18, 0) -
                   np.where((h >= 11) & (h <= 15), 0.12, 0))
    spot_prices = np.clip(spot_mean + daily_cycle + np.random.normal(0, spot_sigma, hours), 0.0, 1.5)

    if pv_cap > 0:
        pv_curve = np.maximum(0, np.sin((h - 6) * np.pi / 12))
        pv_gen = pv_cap * 1000 * pv_curve * 0.85
        forecast = pv_gen
        actual = pv_gen * np.maximum(0, (1 + np.random.normal(0, deviation_sigma, hours)))

        deviation = np.abs(actual - forecast)
        penalized = np.maximum(0, deviation - forecast * deviation_threshold)
        penalty = penalized * spot_prices * penalty_multiplier

        # 落实二选一结算策略
        if feed_mode == "竞价成功：80%机制电价 + 20%现货":
            mech_rev = actual * 0.8 * mech_price
            spot_rev = actual * 0.2 * spot_prices
        else:
            mech_rev = np.zeros(hours)
            spot_rev = actual * spot_prices
            
    else:
        mech_rev = np.zeros(hours)
        spot_rev = np.zeros(hours)
        penalty = np.zeros(hours)

    return spot_prices, mech_rev, spot_rev, penalty

spot_prices, mech_rev, spot_rev, penalty = simulate_spot()
total_rev = mech_rev.sum() + spot_rev.sum()
total_penalty = penalty.sum()
net_rev_30d = total_rev - total_penalty
dev_penalty_annual_wan = (total_penalty * (365 / 30)) / 10000.0

# ================= 20年全投资现金流模型 =================
def build_20y():
    lp = np.array([0.5,0.45,0.42,0.4,0.45,0.55,0.75,0.95,1.05,1.1,1.05,0.95,0.9,0.88,0.92,0.98,1.08,1.15,1.1,0.95,0.8,0.7,0.6,0.55])
    pc = np.array([0,0,0,0,0,0.05,0.15,0.35,0.65,0.85,0.98,1.0,0.95,0.98,0.85,0.6,0.3,0.15,0.05,0,0,0,0,0])
    h24 = np.arange(24)
    hourly_load = lp / lp.sum() * (park_total_elec * 10000 / 365)
    pv_share = pc / pc.sum()
    charge_mask = (h24 <= 5) | ((h24 >= 12) & (h24 <= 13))

    capex = pv_cap * PV_COST + ess_cap * ESS_COST + (ev_cap * EV_COST / 10000.0)
    loan = capex * LOAN_RATIO
    if loan > 0 and LOAN_RATE > 0:
        k = LOAN_RATE * (1 + LOAN_RATE) ** LOAN_TERM / ((1 + LOAN_RATE) ** LOAN_TERM - 1)
        annual_payment = loan * k
    else:
        annual_payment = 0.0

    demand_floor = trans_cap * 0.4
    max_allowable_reduction = max(0.0, current_demand - demand_floor)
    actual_red = min(float(demand_reduction), max_allowable_reduction)
    demand_rev = actual_red * demand_price * 12 / 10000.0

    ev_rev = (ev_cap * EV_HOURS * EV_FEE * 335 / 10000.0) if ev_cap > 0 else 0.0
    weighted_spread = (8 / 12) * spread_normal + (4 / 12) * spread_peak

    cum, cum_share, payback, cum_list = 0.0, 0.0, None, []
    om_cost = (pv_cap * 3.5) + (ess_cap * 1.5) + (ev_cap * EV_COST / 10000.0 * 0.02) + (5.0 if capex > 0 else 0.0)

    # 确定年度余电上网均价
    if feed_mode == "竞价成功：80%机制电价 + 20%现货":
        export_price_annual = 0.8 * mech_price + 0.2 * spot_mean
    else:
        export_price_annual = spot_mean

    for y in range(1, 21):
        deg_pv = (1 - pv_deg / 100.0) ** (y - 1) if pv_cap > 0 else 0.0
        deg_ess = (1 - ess_deg / 100.0) ** (y - 1) if ess_cap > 0 else 0.0
        
        if pv_cap > 0:
            pv_h = pv_cap * 1000 * (PV_HOURS / 365.0) * deg_pv * pv_share
            self_use = np.minimum(pv_h, hourly_load)
            export = np.minimum(np.maximum(0.0, pv_h - hourly_load), trans_cap * 0.5)
            y_pv_rev = ((self_use * price_flat).sum() + (export * export_price_annual).sum()) * 365.0 / 10000.0
        else:
            self_use = np.zeros(24)
            y_pv_rev = 0.0

        if ess_cap > 0:
            max_charge = np.sum(np.where(charge_mask, np.minimum(ess_cap * 500.0, np.maximum(0.0, trans_cap * 0.9 - hourly_load + self_use)), 0.0))
            max_discharge = np.sum(np.where(~charge_mask, np.minimum(hourly_load - self_use, ess_cap * 500.0), 0.0))
            actual_ess = min(ess_cap * 1000.0 * ess_cycle * 0.85 * deg_ess, max_discharge, max_charge * 0.85)
            y_ess_rev = actual_ess * 330.0 * weighted_spread / 10000.0
        else:
            y_ess_rev = 0.0

        gross = (y_pv_rev + y_ess_rev) * annual_factor + demand_rev + ev_rev
        net_full = gross - om_cost - dev_penalty_annual_wan
        cum += net_full
        cum_list.append(cum)

        if payback is None and capex > 0 and cum >= capex:
            payback = y
        cum_share += net_full - (annual_payment if y <= LOAN_TERM else 0.0)

    payback_display = "无新增资产" if capex == 0 else (f"{payback} 年" if payback else "超20年")
    return capex, payback_display, cum / 20.0, cum_share, cum_list, y_pv_rev, y_ess_rev, demand_rev, ev_rev, om_cost, export_price_annual

capex, payback_display, avg_net, cum_share, cum_list, y_pv, y_ess, y_dem, y_ev, om_cost, export_price_annual = build_20y()

# ================= 蒙特卡洛 VaR 与冰冻周压力测试 =================
np.random.seed(7)
mc = [(total_rev * np.random.normal(1, 0.15)) - (total_penalty * abs(np.random.normal(1, 0.3))) for _ in range(2000)]
mc = np.array(mc) / 10000.0 
p5 = np.percentile(mc, 5)
var95 = (net_rev_30d / 10000.0) - p5

F_week = pv_cap * 1000.0 * (PV_HOURS / 365.0) * 7.0
A_week = F_week * (1 - ice_pv_drop)
surge_price = np.clip(spot_mean * (1 + ice_price_surge), 0.0, 1.5)

if feed_mode == "竞价成功：80%机制电价 + 20%现货":
    ice_rev = A_week * 0.8 * mech_price + A_week * 0.2 * surge_price
else:
    ice_rev = A_week * surge_price
    
ice_dev = np.maximum(0.0, (F_week - A_week) - deviation_threshold * F_week)
ice_penalty = ice_dev * surge_price * penalty_multiplier
ice_net = ice_rev - ice_penalty

ice_net_wan = ice_net / 10000.0
ice_penalty_wan = ice_penalty / 10000.0
normal_week = avg_net / 52.0
ice_shrink = ((normal_week - ice_net_wan) / normal_week * 100.0) if normal_week > 0 else 0.0

# ================= 前端可视化 =================
r1c1, r1c2, r1c3, r1c4 = st.columns(4)
r1c1.metric("静态总投资", f"{capex:.1f} 万元")
r1c2.metric("全投资回本期", payback_display)
r1c3.metric("20年均税前净收益", f"{avg_net:.1f} 万元/年")
r1c4.metric("20年累计股东净现金流", f"{cum_share:.1f} 万元", "扣除70%贷款本息")

r2c1, r2c2, r2c3, r2c4 = st.columns(4)
r2c1.metric("偏差考核年罚款期望", f"{dev_penalty_annual_wan:.2f} 万元", "⚠️ 现货偏差敞口", delta_color="inverse")
r2c2.metric("30天 VaR95 风险价值", f"{var95:.2f} 万元", f"P5极端收益 {p5:.2f} 万", delta_color="inverse")
r2c3.metric("冰冻周净收益", f"{ice_net_wan:.2f} 万元", "⚠️ 极端气象考验", delta_color="inverse")
r2c4.metric("冰冻周收益缩水幅度", f"{ice_shrink:.1f} %", delta_color="inverse")

st.markdown("### 📉 20年累计净现金流与投资回收轨迹")
fig_cum = go.Figure(go.Scatter(x=list(range(1, 21)), y=cum_list, mode='lines+markers', name='累计净现金流', line=dict(color='#2563eb', width=2.5)))
if capex > 0:
    fig_cum.add_hline(y=capex, line_dash="dash", line_color="red", annotation_text=f"初始总投资 ({capex:.1f} 万元)", annotation_position="bottom right")
fig_cum.update_layout(height=380, xaxis_title="运营年份", yaxis_title="累计净现金流 (万元)", template="plotly_white", hovermode="x unified")
st.plotly_chart(fig_cum, use_container_width=True)

st.markdown(f"### 📈 湖南现货'鸭形曲线'与光伏余电价格对冲模拟 (综合折算上网价: {export_price_annual:.3f}元)")
fig_p = go.Figure(go.Scatter(y=spot_prices, mode='lines', name='现货节点日前电价', line=dict(color='#ef4444', width=1.2), opacity=0.7))
if feed_mode == "竞价成功：80%机制电价 + 20%现货":
    fig_p.add_hline(y=mech_price, line_dash="dash", line_color="#16a34a", annotation_text=f"机制基准价 ({mech_price}元/kWh)")
fig_p.add_hline(y=price_valley, line_dash="dot", line_color="#f59e0b", annotation_text=f"午间低谷电价 ({price_valley}元/kWh)")
fig_p.update_layout(height=380, xaxis_title="模拟小时 (连续30天)", yaxis_title="电价 (元/kWh)", template="plotly_white")
st.plotly_chart(fig_p, use_container_width=True)

st.markdown("### 🌀 冰冻周极端压力测试 (湖南冬季特色)")
st.caption("情景模拟：日前按常态申报出力，冰冻周光伏覆冰出力骤降，冬季紧供导致实时机制现货价格飙升。")
sc1, sc2, sc3 = st.columns(3)
sc1.metric("常态周均净收益", f"{normal_week:.2f} 万元")
sc2.metric("冰冻周净收益", f"{ice_net_wan:.2f} 万元", delta_color="inverse")
sc3.metric("冰冻周偏差罚款", f"{ice_penalty_wan:.2f} 万元", delta_color="inverse")

fig_ice = go.Figure(go.Bar(
    x=['常态周均净收益', '冰冻周净收益', '冰冻周偏差考核罚款'],
    y=[normal_week, ice_net_wan, ice_penalty_wan],
    marker_color=['#16a34a', '#dc2626', '#f59e0b'],
    text=[f"{normal_week:.2f}万", f"{ice_net_wan:.2f}万", f"{ice_penalty_wan:.2f}万"], textposition='auto'
))
fig_ice.update_layout(height=350, yaxis_title="金额 (万元)", template="plotly_white")
st.plotly_chart(fig_ice, use_container_width=True)

st.markdown("### ⚖️ 首年收益构成与扣减瀑布图")
fig_w = go.Figure(go.Waterfall(
    name="年度收益流", orientation="v", measure=["relative", "relative", "relative", "relative", "relative", "relative", "total"],
    x=['光伏(含余电入市)', '储能套利', '需量管理', '充电服务', '运维成本', '偏差罚款', '年度净收益'],
    y=[y_pv, y_ess, y_dem, y_ev, -om_cost, -dev_penalty_annual_wan, (y_pv + y_ess + y_dem + y_ev - om_cost - dev_penalty_annual_wan)],
    connector={"line": {"color": "rgb(63, 63, 63)"}}
))
fig_w.update_layout(title="年度首年收益与成本构成分解 (万元)", template="plotly_white")
st.plotly_chart(fig_w, use_container_width=True)

# ================= 专家策略与法律边界分析报告 =================
st.markdown("---")
st.header("📜 专家策略与第四监管周期合规报告（2026年8月最新版）")

st.subheader("1. 现货敞口对冲与机制电价结算规则落实")
if feed_mode == "竞价成功：80%机制电价 + 20%现货":
    st.success(f"**✅ 稳健型结算 (竞价成功)**：当前模型严格适用**增量光伏项目上网电量的80%享受机制电价（{mech_price}元）**。在湖南省 4 月至 6 月现货市场均价低迷（低至 0.075-0.15 元）的大环境下，该方案利用 80% 的机制电价作为“压舱石”，能够大幅对冲汛期负电价或低谷击穿成本线的财务风险。")
else:
    st.warning(f"**⚠️ 激进型敞口 (全额现货)**：当前模型适用**未参与竞价的全现货结算**。参照湖南 2026 年二季度现货结算水平（约 {spot_mean} 元），汛期余电上网收益面临严重缩水。建议通过储能错峰放电、或尽快获取指标参与竞价获取机制电价保障。")

st.subheader("2. 需量管理红线与第四监管周期影响")
st.info("**⚖️ 发改价格〔2026〕1077号文风险提示**")
st.markdown("""
2026年8月1日起执行的**第四监管周期**输配电价结构调整（容量/需量电价权重大幅上升），赋予了本项目中“需量压降”模块更高的经济价值。在合同草拟与执行中应注意：
1. **需量 40% 刚性红线未变**：申报最大需量不得低于变压器容量的 40%。EMC 合同中需明确约定：因业主方负荷非受控骤降导致未达 40% 而触发底线计费，产生的超额基本电费由业主全额承担。
2. **电网反向受阻与弃光免责**：针对湖南部分地区电网承载力红黄预警导致的被动限电，EMC 合同必须约定该部分电量视同自发自用结算，防止投资方遭受违约追索。
3. **极端冰冻天气法定免责**：在并网协议与购售电合同中明确约定湖南冬季雨雪冰冻引发的出力受阻属于《民法典》规定的不可抗力，并设定与气象预警等级联动的偏差免责机制。
""")

st.markdown("---")

# ================= 满足要求3：一键输出测算报告（markdown格式） =================
report_md = f'''# 湖南省园区综合能源电价与现货交易风险量化测算报告

## 1. 项目基础参数
- **变压器容量**：{trans_cap} kVA
- **当前月均申报需量**：{current_demand} kW
- **年总用电量**：{park_total_elec} 万kWh/年
- **光伏装机**：{pv_cap} MW
- **储能装机**：{ess_cap} MWh
- **充电桩装机**：{ev_cap} kW
- **光伏余电入市结算方案**：{feed_mode}

## 2. 投资与收益评估 (20年全生命周期)
- **静态总投资**：{capex:.1f} 万元
- **全投资回本期**：{payback_display}
- **20年均税前净收益**：{avg_net:.1f} 万元/年
- **20年累计股东净现金流**：{cum_share:.1f} 万元 (扣除70%贷款本息)
- **偏差考核年罚款期望**：{dev_penalty_annual_wan:.2f} 万元

## 3. 风险与极端情景压力测试
- **30天 VaR95 风险价值**：{var95:.2f} 万元
- **P5 极端收益**：{p5:.2f} 万元
- **常态周均净收益**：{normal_week:.2f} 万元
- **冰冻周极端净收益**：{ice_net_wan:.2f} 万元 (冰冻周收益缩水幅度：{ice_shrink:.1f}%)

## 4. 专家策略与合规报告
- **现货敞口对冲与机制电价结算规则落实**：{"(竞价成功) 稳健型结算：当前模型严格适用增量光伏项目上网电量的80%享受机制电价。利用 80% 的机制电价作为压舱石，能够大幅对冲汛期负电价或低谷击穿成本线的财务风险。" if "竞价成功" in feed_mode else "(全额现货) 激进型敞口：当前模型适用未参与竞价的全现货结算。汛期余电上网收益面临严重缩水，建议通过储能错峰放电、或尽快获取指标参与竞价。"}
- **需量管理红线提示**：需量 40% 刚性红线未变，申报最大需量不得低于变压器容量的 40%。极端冰冻天气法定免责，需在协议中明确约定。

> 本测算模型参照2026年8月施行的最新政策文件。测算结果供论证及风险对冲参考，实际结算以湖南电力交易中心正式出具的结算单为准。
'''

st.download_button(
    label="📄 一键输出测算报告（Markdown格式）",
    data=report_md,
    file_name="湖南园区综合能源测算报告.md",
    mime="text/markdown",
    use_container_width=True
)

st.caption("⚖️ 免责声明：本模型已完全同步2026年8月施行的发改价格〔2026〕1077号/湘发改价调〔2026〕460号文件，测算结果供投资论证及风险对冲参考。实际结算以湖南电力交易中心正式出具的结算单为准。")
