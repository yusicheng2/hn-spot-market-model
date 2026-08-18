import streamlit as st
import numpy as np
import plotly.graph_objects as go

# ================= 页面配置 =================
st.set_page_config(page_title="湖南园区光储充现货交易风险量化模型", layout="wide")

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

st.title("⚡ 湖南省园区综合能源电价与现货交易风险量化模型 (第四监管周期专家版 v1.5)")
st.caption("v1.5 核心调优：修复风险引擎储能收益遗漏 ｜ 纳入园区让利双模式刚性扣减 ｜ 完善冰冻周/蒙特卡洛压力测试")
st.markdown("---")

# ================= 侧边栏：园区参数（湖南园区） =================
st.sidebar.header("📊 园区参数设定")

st.sidebar.subheader("1. 物理资产与需量管理")
trans_cap = st.sidebar.slider("变压器容量 (kVA)", 1000, 20000, 8000, 500)
current_demand = st.sidebar.slider("当前月均申报需量 (kW)", 1000, 15000, 5000, 250)
demand_reduction = st.sidebar.slider("需量压降目标 (kW)", 0, 2000, 800, 50)
demand_price = st.sidebar.slider("需量电费单价 (元/kW·月)", 20.0, 60.0, 35.4, 0.5)

park_total_elec = st.sidebar.slider("年总用电量 (万kWh/年)", 500, 20000, 2500, 500)

pv_cap = st.sidebar.slider("光伏装机 (MW)", 0.0, 20.0, 6.0, 0.5)
ess_cap = st.sidebar.slider("储能装机 (MWh)", 0.0, 50.0, 15.0, 1.0)
ess_cycle = st.sidebar.slider("储能日循环次数", 0.5, 2.5, 1.9, 0.1)
ev_cap = st.sidebar.slider("充电桩装机 (kW)", 0, 10000, 4000, 500)

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
spot_mean = st.sidebar.slider("现货日前均价期望 (元/kWh)", 0.01, 0.55, 0.10, 0.01)
spot_sigma = st.sidebar.slider("现货价格波动率 (Sigma)", 0.05, 0.30, 0.15, 0.01)

# ================= 新增：园区收益分成模块 =================
st.sidebar.subheader("4. 园区收益分成刚性成本 (二选一)")
share_mode = st.sidebar.radio(
    "收益分成计算模式",
    ["模式一：按年总用电量分成", "模式二：按定额折扣优惠"]
)

if share_mode == "模式一：按年总用电量分成":
    share_vol = st.sidebar.number_input("年用电量基准 (万kWh, 封顶4000)", min_value=0, max_value=4000, value=2500, step=100)
    share_price = st.sidebar.number_input("度电单价让利 (元/kWh, 封顶0.10)", min_value=0.00, max_value=0.10, value=0.06, step=0.01)
    annual_share_cost = share_vol * share_price  # 单位：万元
else:
    share_fixed = st.sidebar.number_input("年让利总金额 (万元, 封顶500)", min_value=0, max_value=500, value=150, step=10)
    annual_share_cost = share_fixed  # 单位：万元

st.sidebar.subheader("5. 衰减因子与偏差考核")
pv_deg = st.sidebar.slider("光伏年衰减率 (%)", 0.1, 2.0, 0.5, 0.1)
ess_deg = st.sidebar.slider("储能年衰减率 (%)", 0.5, 5.0, 2.0, 0.5)
deviation_sigma = st.sidebar.slider("光伏预测误差标准差 (%)", 2.0, 20.0, 8.0, 1.0) / 100.0
penalty_multiplier = st.sidebar.slider("偏差惩罚倍数 (实时电价)", 1.0, 3.0, 1.5, 0.1)
deviation_threshold = st.sidebar.slider("免考核死区 (%)", 0.0, 10.0, 3.0, 0.5) / 100.0

st.sidebar.subheader("6. 年化校准与冰冻周压力测试")
annual_factor = st.sidebar.slider("年化折算系数 (汛期弃光/受阻折减)", 0.60, 1.00, 0.80, 0.05)
ice_pv_drop = st.sidebar.slider("冰冻周光伏出力骤降 (%)", 0, 90, 60, 5) / 100.0
ice_price_surge = st.sidebar.slider("冰冻周现货电价飙升 (%)", 0, 150, 60, 5) / 100.0

st.sidebar.markdown("---")
st.sidebar.info("💡 尽调提示：已将业主收益分成确认为项目刚性负债，并同步扣减于单月现金流、冰冻周测试及全生命周期财务台账中。")

# ================= 财务与工程常量 =================
PV_HOURS = 1000.0                      
LOAN_RATIO, LOAN_RATE, LOAN_TERM = 0.70, 0.045, 10 
PV_COST, ESS_COST, EV_COST = 280.0, 70.0, 700.0    
EV_HOURS, EV_FEE = 3.0, 0.45           

# ================= 30天光伏现货价格与偏差模拟 =================
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
    else:
        penalty = np.zeros(hours)

    return spot_prices, penalty

spot_prices, penalty = simulate_spot()
dev_penalty_annual_wan = (penalty.sum() * (365 / 30)) / 10000.0

# ================= 20年全投资现金流模型 (修复漏算问题) =================
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
        # 核心修复：在此严格扣除运维成本和园区收益分成
        net_full = gross - om_cost - dev_penalty_annual_wan - annual_share_cost
        
        cum += net_full
        cum_list.append(cum)

        if payback is None and capex > 0 and cum >= capex:
            payback = y + (capex - (cum - net_full)) / net_full if net_full > 0 else y
            
        cum_share += net_full - (annual_payment if y <= LOAN_TERM else 0.0)

    payback_display = "无新增资产" if capex == 0 else (f"{payback:.1f} 年" if payback else "超20年 (面临倒挂)")
    return capex, payback_display, cum / 20.0, cum_share, cum_list, y_pv_rev, y_ess_rev, demand_rev, ev_rev, om_cost, export_price_annual

capex, payback_display, avg_net, cum_share, cum_list, y_pv, y_ess, y_dem, y_ev, om_cost, export_price_annual = build_20y()
total_share_cost_20y = annual_share_cost * 20.0

# ================= 蒙特卡洛 VaR 与冰冻周压力测试 (修复测算逻辑) =================
# 将年化基准收益平摊至单月
monthly_base_pv = y_pv / 12.0
monthly_base_other = (y_ess + y_dem + y_ev) / 12.0
monthly_fixed_costs = (om_cost + annual_share_cost) / 12.0
monthly_base_penalty = dev_penalty_annual_wan / 12.0

np.random.seed(7)
mc = []
for _ in range(2000):
    price_f = np.random.normal(1.0, 0.15)
    dev_f = np.abs(np.random.normal(1.0, 0.3))
    # 模拟净收益：仅光伏收益和罚款受天气与电价波动，储能及充放电为固定现金流，并刚性扣除成本
    sim_net = (monthly_base_pv * price_f) + monthly_base_other - (monthly_base_penalty * dev_f * penalty_multiplier) - monthly_fixed_costs
    mc.append(sim_net)

mc_arr = np.array(mc)
p5 = np.percentile(mc_arr, 5)
base_monthly_net = monthly_base_pv + monthly_base_other - monthly_base_penalty - monthly_fixed_costs
var95 = base_monthly_net - p5

# 冰冻周测算
F_week = pv_cap * 1000.0 * (PV_HOURS / 365.0) * 7.0
A_week = F_week * (1 - ice_pv_drop)
surge_price = np.clip(spot_mean * (1 + ice_price_surge), 0.0, 1.5)

if feed_mode == "竞价成功：80%机制电价 + 20%现货":
    ice_pv_rev_yuan = A_week * 0.8 * mech_price + A_week * 0.2 * surge_price
else:
    ice_pv_rev_yuan = A_week * surge_price
    
ice_dev = np.maximum(0.0, (F_week - A_week) - deviation_threshold * F_week)
ice_penalty_yuan = ice_dev * surge_price * penalty_multiplier

ice_pv_wan = ice_pv_rev_yuan / 10000.0
ice_penalty_wan = ice_penalty_yuan / 10000.0
ice_other_wan = (y_ess + y_dem + y_ev) * 7.0 / 365.0
ice_costs_wan = (om_cost + annual_share_cost) * 7.0 / 365.0

# 冰冻周核心净利
ice_net_wan = ice_pv_wan + ice_other_wan - ice_penalty_wan - ice_costs_wan
normal_week = avg_net / 52.0
ice_shrink = ((normal_week - ice_net_wan) / normal_week * 100.0) if normal_week > 0 else 0.0

# ================= 前端可视化 =================
st.error(f"⚠️ **风控提示**：全生命周期内，项目需向园区支付高达 **{total_share_cost_20y:.1f} 万元** 的刚性分成。当前所有回本期及压力测试已将其全量剥离。")

r1c1, r1c2, r1c3, r1c4 = st.columns(4)
r1c1.metric("静态总投资", f"{capex:.1f} 万元")
r1c2.metric("全投资回本期", payback_display)
r1c3.metric("20年均税前净收益", f"{avg_net:.1f} 万元/年")
r1c4.metric("20年累计股东现金流", f"{cum_share:.1f} 万元", "扣除70%贷款本息")

r2c1, r2c2, r2c3, r2c4 = st.columns(4)
r2c1.metric("偏差考核年罚款期望", f"{dev_penalty_annual_wan:.2f} 万元", "⚠️ 现货偏差敞口", delta_color="inverse")
r2c2.metric("单月 VaR95 风险价值", f"{var95:.2f} 万元", f"单月P5极端收益 {p5:.2f} 万", delta_color="inverse")
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

st.markdown("### ⚖️ 首年收益构成与刚性扣减瀑布图")
fig_w = go.Figure(go.Waterfall(
    name="年度收益流", orientation="v", measure=["relative", "relative", "relative", "relative", "relative", "relative", "relative", "total"],
    x=['光伏(含自用+上网)', '储能套利', '需量管理', '充电服务', '物理运维', '偏差罚款', '园区收益让渡', '年度净收益'],
    y=[y_pv, y_ess, y_dem, y_ev, -om_cost, -dev_penalty_annual_wan, -annual_share_cost, (y_pv + y_ess + y_dem + y_ev - om_cost - dev_penalty_annual_wan - annual_share_cost)],
    connector={"line": {"color": "rgb(63, 63, 63)"}}
))
fig_w.update_layout(title="年度首年收益与成本构成分解 (万元)", template="plotly_white")
st.plotly_chart(fig_w, use_container_width=True)

# ================= 专家策略与法律边界分析报告 =================
st.markdown("---")
st.header("📜 专家策略与第四监管周期合规报告（2026年8月最新版）")

st.subheader("1. 收益分成条款的“倒挂陷阱”防控")
if share_mode == "模式二：按定额折扣优惠":
    st.error(f"**核心预警 (定额让利风险)**：您设定了每年向园区定额支付 {share_fixed} 万元。在现货市场频繁出现负电价，或遭遇湖南冬春季恶劣冰冻天气导致停机的极端情境下，该笔定额支出将直接导致项目公司现金流断裂。")
    st.info("**风控建议**：在《能源管理合同》中，必须摒弃“定额保底”，强行植入“兜底保障免除机制”。约定当现货结算电价低于特定红线，或发生极端天气减产时，投资方享有暂停或等比例折减支付定额收益的抗辩权。")
else:
    st.success(f"**结构评价 (按电量分成)**：按 {share_vol}万度基准 与 {share_price}元单价 联动的分成模式相对稳健，让资产端与业主的利益实现风险共担，有效缓释了现金流挤兑风险。")

st.subheader("2. 现货敞口对冲与机制电价规则")
if "竞价成功" in feed_mode:
    st.success(f"**✅ 稳健型结算**：当前严格落实了**光伏上网电量 80% 享受机制电价（{mech_price}元）**。这是抵御现货批发市场汛期超低价的唯一护城河。")
else:
    st.warning(f"**⚠️ 激进型敞口**：**全现货结算**将导致汛期余电上网收益面临严重缩水。建议通过储能错峰放电、或尽快获取指标参与竞价。")

st.subheader("3. 需量管理红线与法务边界")
st.markdown("""
1. **需量 40% 刚性红线**：申报最大需量不得低于变压器容量的 40%。EMC 合同中需明确约定：因业主方负荷非受控骤降引发的超额基本电费由业主全额承担。
2. **极端冰冻天气法定免责**：在并网协议中必须明确约定湖南冬季雨雪冰冻引发的出力受阻属于不可抗力，并设定与气象预警等级联动的现货偏差考核免责机制，防止罚单单方穿透给投资方。
""")

st.markdown("---")

# ================= 一键输出测算报告 =================
report_md = f'''# 湖南省园区综合能源电价与现货交易风险量化测算报告

## 1. 项目基础档案
- **变压器容量**：{trans_cap} kVA
- **当前月均申报需量**：{current_demand} kW
- **光伏/储能/充电桩装机**：{pv_cap} MW / {ess_cap} MWh / {ev_cap} kW
- **光伏余电入市结算方案**：{feed_mode}
- **园区收益分成模式**：{share_mode} (年刚性支出 {annual_share_cost} 万元)

## 2. 穿透式财务测算 (20年全生命周期)
- **初始静态总投资**：{capex:.1f} 万元
- **全投资动态回本期**：{payback_display}
- **20年均税前净收益**：{avg_net:.1f} 万元/年 (已剥离运维与园区让利)
- **20年累计股东净现金流**：{cum_share:.1f} 万元 (扣除70%贷款本息)
- **园区分成总支出(20年)**：{total_share_cost_20y:.1f} 万元

## 3. 极端情景压力测试
- **单月 VaR95 风险价值**：{var95:.2f} 万元
- **常态周均净收益**：{normal_week:.2f} 万元
- **冰冻周极端净收益**：{ice_net_wan:.2f} 万元 (冰冻周收益缩水幅度：{ice_shrink:.1f}%)

## 4. 合同风控与法律边界分析
- **收益分成“倒挂”防范**：{"在EMC合同中须加入“兜底保障免除机制”，防范定额分成的断链风险。" if "定额" in share_mode else "电量比例分成相对稳健，实现了双方风险共担。"}
- **现货敞口对冲**：{"稳健型：80% 机制电价有效对冲汛期负电价风险。" if "竞价成功" in feed_mode else "激进型：全现货敞口极高，需通过储能套利严格对冲。"}
- **偏差罚金传导**：不可单方兜底偏差责任，因业主非计划限产引发的考核罚单应予以追偿。

> 本测算模型参照2026年8月施行的最新湖南省政策文件及第四监管周期规则。测算结果供投资论证及风险对冲参考，实际结算以电力交易中心正式结算单为准。
'''

st.download_button(
    label="📄 一键输出测算及风控报告（Markdown格式）",
    data=report_md,
    file_name="湖南园区光储充综合测算防线报告.md",
    mime="text/markdown",
    use_container_width=True
)
