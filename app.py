import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ================= 页面配置 =================
st.set_page_config(page_title="广东园区光储现货交易风险量化模型", layout="wide")
st.title("⚡ 广东省园区综合能源现货交易风险量化与对冲模型 (专家版 v4.0)")
st.caption("v4.0 核心调优：园区收益分成刚性成本全量剥离 ｜ 20年累计支出显化 ｜ 深度法律与合规风险穿透分析")
st.markdown("---")

# ================= 侧边栏：参数输入 =================
st.sidebar.header("📊 园区资产与交易参数设定")

st.sidebar.subheader("1. 物理资产参数")
pv_cap = st.sidebar.slider("光伏装机 (MW)", 0.0, 20.0, 6.0, 0.5)
# 修正基准：广东地区实际有效时长约1100小时
pv_hours = st.sidebar.number_input("光伏年等效利用小时 (h)", value=1100, step=50)
ess_cap = st.sidebar.slider("储能装机 (MWh)", 0.0, 50.0, 15.0, 1.0)
ess_power = st.sidebar.slider("储能功率 (MW)", 0.0, 20.0, 5.0, 0.5)
park_load = st.sidebar.slider("园区日均基础负荷 (MWh)", 10, 100, 45, 5)

st.sidebar.subheader("1.5 园区电价参数")
retail_price = st.sidebar.number_input("园区综合购电单价 (元/kWh)", value=0.75, step=0.01)

st.sidebar.subheader("2. 增量光伏余电上网价格模式 (二选一)")
# 修正表述：增量光伏项目上网电量的80%享受机制电价
feed_mode = st.sidebar.radio(
    "光伏余电入市结算方案",
    ["竞价成功：增量光伏项目上网电量的80%享受机制电价", "未参与竞价：全额现货市场价"],
    help="依据广东现行政策，竞价成功者享受机制电价；否则余电全额按现货节点电价结算。"
)
mech_price = st.sidebar.number_input("广东机制电价 (元/kWh)", value=0.453, step=0.005)
spot_mean = st.sidebar.slider("现货日前市场均价期望 (元/kWh)", 0.15, 0.55, 0.25, 0.01)
spot_sigma = st.sidebar.slider("现货价格波动率 (Sigma)", 0.05, 0.30, 0.15, 0.01)

st.sidebar.subheader("3. 偏差考核与风险参数 (双细则)")
deviation_sigma = st.sidebar.slider("光伏预测误差标准差 (%)", 2.0, 20.0, 8.0, 1.0) / 100.0
penalty_multiplier = st.sidebar.slider("偏差惩罚倍数 (实时电价)", 1.0, 3.0, 1.5, 0.1)
deviation_threshold = st.sidebar.slider("免考核死区 (%)", 0.0, 10.0, 5.0, 0.5) / 100.0

st.sidebar.subheader("4. 年化校准与压力情景")
annual_factor = st.sidebar.slider("年化折算系数 (仅限台风季光伏折减)", 0.60, 1.00, 0.80, 0.05)
typhoon_pv_drop = st.sidebar.slider("台风周光伏出力骤降 (%)", 0, 90, 60, 5) / 100.0
typhoon_price_drop = st.sidebar.slider("台风周现货电价骤降 (%)", 0, 90, 70, 5) / 100.0

# ================= 新增：园区收益分成模块 =================
st.sidebar.subheader("5. 园区收益分成刚性成本 (二选一)")
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

st.sidebar.subheader("6. 衰减因子与刚性运营成本")
pv_deg = st.sidebar.number_input("光伏组件年均衰减率 (%)", value=0.5, step=0.1)
ess_deg = st.sidebar.number_input("储能电池年衰减率 (%)", value=2.0, step=0.1)
dev_fee = st.sidebar.number_input("园区路条/前期开发费 (万元)", value=200, step=10)
cont_fee = st.sidebar.number_input("不可预见费用 (万元)", value=50, step=10)
land_rent = st.sidebar.number_input("场地租金 (万元/年)", value=10, step=1)
pv_om = st.sidebar.number_input("光伏运维费 (万元/MW/年)", value=5, step=1)
ess_om = st.sidebar.number_input("储能运维费 (万元/年)", value=20, step=1)

st.sidebar.subheader("7. 储能工商业核心收益参数")
ess_spread = st.sidebar.number_input("广东储能综合峰谷价差 (元/kWh)", value=1.15, step=0.01)
ess_cycles = st.sidebar.number_input("储能日均循环次数", value=1.9, step=0.05)
demand_price = st.sidebar.number_input("需量单价降本 (元/kW·月)", value=39.0, step=1.0)

st.sidebar.markdown("---")
st.sidebar.info("💡 尽调提示：已强行将业主收益分成确认为刚性负债，并同步扣减于单月现金流、台风测试及全生命周期财务台账中。")

# ================= 后端核心计算引擎（蒙特卡洛模拟） =================
def simulate_market_and_risk(days=30, steps=24):
    np.random.seed(42)
    hours = days * steps
    t = np.arange(hours)

    daily_cycle = 0.15 * np.sin((t % 24 - 6) * np.pi / 12)
    spot_prices = spot_mean + daily_cycle + np.random.normal(0, spot_sigma, hours)
    spot_prices = np.clip(spot_prices, 0.0, 1.5)

    hourly_load = (park_load * 1000) / 24.0
    base_pv_curve = np.maximum(0, np.sin((t % 24 - 6) * np.pi / 12))
    daily_base_sum = base_pv_curve[:24].sum()
    
    if pv_cap > 0 and daily_base_sum > 0:
        norm_factor = (pv_hours / 365.0) / daily_base_sum
        pv_generation = pv_cap * 1000 * base_pv_curve * norm_factor
        prediction_error = np.random.normal(0, deviation_sigma, hours)
        pv_actual = pv_generation * np.maximum(0, (1 + prediction_error))
        pv_forecast = pv_generation
        
        # 偏差考核
        deviation = np.abs(pv_actual - pv_forecast)
        threshold_kwh = pv_forecast * deviation_threshold
        penalized_deviation = np.maximum(0, deviation - threshold_kwh)
        penalty_cost = penalized_deviation * spot_prices * penalty_multiplier

        # 光伏发用分离
        self_consume = np.minimum(pv_actual, hourly_load)
        exported = pv_actual - self_consume
        self_consume_rev = self_consume * retail_price 

        if "机制电价" in feed_mode:
            mech_revenue = exported * 0.8 * mech_price
            spot_revenue = exported * 0.2 * spot_prices
        else:
            mech_revenue = np.zeros(hours)
            spot_revenue = exported * spot_prices
    else:
        pv_forecast = np.zeros(hours)
        pv_actual = np.zeros(hours)
        self_consume_rev = np.zeros(hours)
        mech_revenue = np.zeros(hours)
        spot_revenue = np.zeros(hours)
        penalty_cost = np.zeros(hours)

    # 储能零售端结算
    if ess_cap > 0 and ess_power > 0:
        monthly_ess_arb = ess_cap * 1000 * ess_cycles * days * ess_spread
        monthly_ess_demand = ess_power * 1000 * demand_price
        hourly_ess_total_rev = (monthly_ess_arb + monthly_ess_demand) / hours
        ess_revenue = np.full(hours, hourly_ess_total_rev)
        
        st.session_state['temp_monthly_arb'] = monthly_ess_arb
        st.session_state['temp_monthly_demand'] = monthly_ess_demand
    else:
        ess_revenue = np.zeros(hours)
        st.session_state['temp_monthly_arb'] = 0.0
        st.session_state['temp_monthly_demand'] = 0.0

    return pd.DataFrame({
        'Hour': t, 'Spot_Price': spot_prices,
        'PV_Forecast': pv_forecast, 'PV_Actual': pv_actual,
        'Self_Consume_Rev': self_consume_rev,
        'Mech_Rev': mech_revenue, 'Spot_Rev': spot_revenue,
        'ESS_Rev': ess_revenue, 'Penalty': penalty_cost
    })

df = simulate_market_and_risk()

# ================= 财务与风险指标 =================
total_rev = df['Self_Consume_Rev'].sum() + df['Mech_Rev'].sum() + df['Spot_Rev'].sum() + df['ESS_Rev'].sum()
total_penalty = df['Penalty'].sum()

# 提取并折算刚性成本
fixed_opex_annual = (pv_cap * pv_om) + ess_om + land_rent  # 万元
monthly_share_cost_rmb = (annual_share_cost * 10000.0) / 12.0
monthly_fixed_opex_rmb = (fixed_opex_annual * 10000.0) / 12.0
weekly_share_cost_rmb = (annual_share_cost * 10000.0) * (7.0 / 365.0)
weekly_fixed_opex_rmb = (fixed_opex_annual * 10000.0) * (7.0 / 365.0)

# 单月净收益（严扣分成与运维）
sim_gross_rev = total_rev - total_penalty
sim_net_rev = sim_gross_rev - monthly_share_cost_rmb - monthly_fixed_opex_rmb

capex = (pv_cap * 280.0 + ess_cap * 70.0) + dev_fee + cont_fee

# 20年全生命周期动态推演
pv_rev_1 = (df['Self_Consume_Rev'].sum() + df['Mech_Rev'].sum() + df['Spot_Rev'].sum()) * (365/30) * annual_factor / 10000.0
ess_rev_1 = df['ESS_Rev'].sum() * (365/30) / 10000.0
penalty_1 = df['Penalty'].sum() * (365/30) * annual_factor / 10000.0

cumulative_cash = 0.0
payback_years = 0.0
total_net_20y = 0.0

for y in range(1, 21):
    p_factor = (1 - pv_deg / 100.0)**(y - 1)
    e_factor = (1 - ess_deg / 100.0)**(y - 1)
    y_rev = (pv_rev_1 * p_factor) + (ess_rev_1 * e_factor) - (penalty_1 * p_factor)
    # 核心修复：按年剥离分成成本及固定运维
    y_net = y_rev - annual_share_cost - fixed_opex_annual
    total_net_20y += y_net
    
    if payback_years == 0:
        cumulative_cash += y_net
        if cumulative_cash >= capex and y_net > 0:
            payback_years = (y - 1) + (capex - (cumulative_cash - y_net)) / y_net

avg_net_20y = total_net_20y / 20.0
total_share_cost_20y = annual_share_cost * 20.0 # 20年累计给园区的钱

if capex == 0:
    payback_display = "无新增资产"
elif payback_years > 0:
    payback_display = f"{payback_years:.1f} 年"
else:
    payback_display = ">20年 (难以回本)"

# 蒙特卡洛 P5 风险价值
np.random.seed(7)
mc_results = []
for _ in range(2000):
    price_f = np.random.normal(1.0, 0.2)
    dev_f = np.abs(np.random.normal(1.0, 0.4))
    sim_gross = ((total_rev - df['ESS_Rev'].sum()) * price_f) + df['ESS_Rev'].sum() - (total_penalty * dev_f * penalty_multiplier)
    # 修复：风险场景下刚性成本照常流失
    sim_net = sim_gross - monthly_share_cost_rmb - monthly_fixed_opex_rmb
    mc_results.append(sim_net / 10000.0)
mc_arr = np.array(mc_results)
p5_value = np.percentile(mc_arr, 5)
var95 = (sim_net_rev / 10000.0) - p5_value

# 台风周极端压力测试 
np.random.seed(99)
t_s = np.arange(7 * 24)
base_pv_curve = np.maximum(0, np.sin((t_s % 24 - 6) * np.pi / 12))
daily_base_sum = base_pv_curve[:24].sum()
hourly_load = (park_load * 1000) / 24.0

if pv_cap > 0 and daily_base_sum > 0:
    norm_factor = (pv_hours / 365.0) / daily_base_sum
    pv_forecast_week = pv_cap * 1000 * base_pv_curve * norm_factor
    pv_actual_week = pv_forecast_week * (1 - typhoon_pv_drop)
    crash_price = np.clip(spot_mean * (1 - typhoon_price_drop), 0.0, 1.5)

    stress_self_consume = np.minimum(pv_actual_week, hourly_load)
    stress_exported = pv_actual_week - stress_self_consume
    stress_self_consume_rev = stress_self_consume.sum() * retail_price

    if "机制电价" in feed_mode:
        stress_revenue = stress_self_consume_rev + (stress_exported * 0.8 * mech_price).sum() + (stress_exported * 0.2 * crash_price).sum()
    else:
        stress_revenue = stress_self_consume_rev + (stress_exported * crash_price).sum()
        
    stress_deviation = np.maximum(0, (pv_forecast_week - pv_actual_week) - deviation_threshold * pv_forecast_week)
    stress_penalty = (stress_deviation * crash_price * penalty_multiplier).sum()
else:
    stress_revenue = 0.0
    stress_penalty = 0.0

stress_ess_rev = df['ESS_Rev'].sum() / (30.0 / 7.0)
# 修复：台风停工/降收期间，按周折算的业主分成与租金不可免除
stress_net = (stress_revenue + stress_ess_rev) - stress_penalty - weekly_share_cost_rmb - weekly_fixed_opex_rmb
normal_week_net = sim_net_rev / (30.0 / 7.0)
stress_shrink_pct = ((normal_week_net - stress_net) / normal_week_net * 100.0) if normal_week_net > 0 else 0.0

# ================= 前端可视化 =================
st.markdown("### 📊 全周期核心指标与利润台账")
# 新增高亮提示20年刚性支出
st.error(f"⚠️ **尽调核心提醒**：在全生命周期内，除设备自然衰减与运维开支外，项目将面临向园区支付高达 **{total_share_cost_20y:.1f} 万元** 的刚性收益分成支出。当前所有测算已严格完成该项剥离。")

col1, col2, col3, col4 = st.columns(4)
col1.metric("20年均税前净利润", f"{avg_net_20y:.1f} 万/年", f"首年净利: {year1_net_rev_10k:.1f} 万")
col2.metric("动态回本期(含衰减)", payback_display, "基于严苛成本模型定标")
col3.metric("偏差考核总罚款(单月)", f"{total_penalty/10000:.2f} 万元", "⚠️ 现货敞口风险", delta_color="inverse")
col4.metric("单月净收益(扣除分成)", f"{sim_net_rev/10000:.2f} 万元", f"极端P5收益 {p5_value:.1f} 万", delta_color="inverse")

st.markdown("### 📉 收益构成与扣款瀑布图 (全量成本口径)")
rev_components = {
    '光伏自发自用抵扣': df['Self_Consume_Rev'].sum(),
    '光伏机制电价收益': df['Mech_Rev'].sum() if "机制电价" in feed_mode else 0,
    '光伏现货敞口收益': df['Spot_Rev'].sum(),
    '储能综合峰谷套利': st.session_state.get('temp_monthly_arb', 0),
    '储能需量降本收益': st.session_state.get('temp_monthly_demand', 0),
    '偏差考核罚款(流失)': -df['Penalty'].sum(),
    '园区收益分成(刚性扣除)': -monthly_share_cost_rmb,
    '固定运维与租金(刚性扣除)': -monthly_fixed_opex_rmb
}
rev_components = {k: v for k, v in rev_components.items() if v != 0}

fig2 = go.Figure(go.Waterfall(
    name="收益瀑布", orientation="v",
    x=list(rev_components.keys()), y=list(rev_components.values()),
    connector={"line": {"color": "rgb(63, 63, 63)"}},
))
fig2.update_layout(height=450, yaxis_title="金额 (元)", template="plotly_white")
st.plotly_chart(fig2, use_container_width=True)

st.markdown("### 🌀 台风周极端压力测试 (广东现货气象特征)")
scol1, scol2, scol3 = st.columns(3)
scol1.metric("正常周均净收益", f"{normal_week_net/10000:.2f} 万元")
scol2.metric("台风周净收益", f"{stress_net/10000:.2f} 万元", delta_color="inverse")
scol3.metric("台风周收益缩水幅度", f"{stress_shrink_pct:.1f} %", delta_color="inverse")

fig_s = go.Figure(go.Bar(
    x=['正常周净收益', '台风周净收益', '其中:台风周偏差罚款'],
    y=[normal_week_net/10000, stress_net/10000, stress_penalty/10000],
    marker_color=['#16a34a', '#dc2626', '#f59e0b'],
    text=[f"{normal_week_net/10000:.2f}万", f"{stress_net/10000:.2f}万", f"{stress_penalty/10000:.2f}万"], textposition='auto'
))
fig_s.update_layout(height=350, yaxis_title="万元", template="plotly_white")
st.plotly_chart(fig_s, use_container_width=True)

# ================= 专家策略与法律边界分析报告 =================
st.markdown("---")
st.header("📜 合同风控与法律边界分析报告")

st.subheader("1. 收益分成条款的“倒挂陷阱”防控")
if share_mode == "模式二：按定额折扣优惠":
    st.error(f"**核心预警 (定额让利模式)**：在本项目中，您设定了每年向园区定额支付 {share_fixed} 万元。从法务实践来看，这是极高风险的架构。因不可抗力（如长时间极端恶劣天气）或现货均价击穿成本线时，若资产端产生亏损，该笔定额支出将直接导致项目公司现金流断裂。")
    st.info("**条款修改建议**：在 EMC 或效益分享协议中，必须摒弃“定额保底”，采用“净利润分配优先劣后”原则；或引入**『兜底保障免除条款 / 收益倒挂触发机制』**，约定当现货市场月均出清价格低于特定红线，或遭遇连续极端气象条件时，投资方享有暂停或等比例折减支付定额收益的抗辩权。")
else:
    st.success(f"**结构评价 (按电量比例分成)**：相比定额支付，按 {share_vol}万度 用电量与 {share_price}元/度 绑定的分成模式具有更好的风险弹性。资产端的收益能力与给业主的让利规模基本保持了同频共振，缓释了资产方的现金流挤兑风险。")

st.subheader("2. 不可抗力与“情势变更”的防御性起草")
st.markdown("""
在现货市场环境下，传统合同中泛泛而谈的“不可抗力”条款已不足以形成有效防御。建议在绿电购销协议中加入基于交易规则的**情势变更细化条款**：
* 明确界定台风（如蓝色及以上预警）、暴雨等导致资产出力骤减的情形，不仅豁免业主的供电考核，且需赋予运营方依据广东电力交易中心规定，**启动免考核申报程序的法定配合权**。
* 若增量光伏无法获得或丧失“上网电量80%享受机制电价”的政策红利（政策发生根本性转向），属于不可归责于双方的情势变更，应保留重新磋商收益分成比例的救济权利。
""")

st.subheader("3. 现货偏差罚金的穿透与隔断")
st.markdown("""
实务中，管理方切忌在商务谈判中包揽所有现货偏差责任。
* 因园区业主自身生产工艺调整、设备突发检修等导致的**非计划性用电负荷剧烈震荡**，进而引发的电能偏差及双细则考核罚金，应在协议中设立追偿机制。这既是风险防火墙，也能倒逼用电方优化其用能计划性。
""")
