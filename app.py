"""Expense Tracker - full app.   Run: streamlit run app.py"""
from datetime import date

import os
from datetime import date
import html
import pandas as pd
import plotly.express as px
import streamlit as st

import db
import utils

st.set_page_config(page_title="Expense Tracker", page_icon="🧾", layout="wide")
db.init_db()

CLASSIC = ["#1F2A44", "#B8923A", "#6B8E7F", "#A4553E", "#8A8D91", "#C9B58A", "#4F6D8F", "#7A5C58"]
px.defaults.color_discrete_sequence = CLASSIC
px.defaults.template = "simple_white"

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&display=swap');
h1, h2, h3 { font-family: 'Playfair Display', Georgia, serif !important; }

/* sidebar */
[data-testid="stSidebar"] { background: #1F2A44; }
[data-testid="stSidebar"] * { color: #EDE6D6; }
[data-testid="stSidebar"] hr { border-color: rgba(237,230,214,.2); }
.brand { font-family: 'Playfair Display', Georgia, serif; font-size: 1.6rem; font-weight: 700;
         letter-spacing: .5px; padding: .5rem 0 1rem; }
.brand span { color: #C9A44C; }
.user-card { background: rgba(255,255,255,.07); border-left: 3px solid #C9A44C;
             border-radius: 6px; padding: .6rem .8rem; margin-bottom: 1.2rem; line-height: 1.3; }
.user-card small { opacity: .7; }

/* menu: hide radio dots, make items look like a clean list */
[data-testid="stSidebar"] div[role="radiogroup"] { gap: 2px; }
[data-testid="stSidebar"] div[role="radiogroup"] label { padding: .55rem .8rem; border-radius: 6px; width: 100%; cursor: pointer; }
[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child { display: none; }
[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background: rgba(255,255,255,.08); }
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
    background: rgba(201,164,76,.18); box-shadow: inset 3px 0 0 #C9A44C; font-weight: 600; }
[data-testid="stSidebar"] .stButton button { background: transparent; border: 1px solid #C9A44C; color: #C9A44C; width: 100%; }
[data-testid="stSidebar"] .stButton button:hover { background: #C9A44C; color: #1F2A44; }

/* metric cards */
[data-testid="stMetric"] { background: rgba(128,128,128,.10); border: 1px solid rgba(128,128,128,.28); border-radius: 8px; padding: .8rem 1rem; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_model(user_id):
    return utils.load_categorizer(user_id)


def money(x, sym):
    return f"{sym}{x:,.2f}"


# ===================================================================== AUTH
def auth_page():
    st.title("🧾 Expense Tracker")
    st.caption("Track income and spending, set budgets, and reach your savings goals.")
    t1, t2 = st.tabs(["Log in", "Register"])
    with t1:
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", type="primary"):
                user = db.authenticate(u, p)
                if user:
                    st.session_state["user_id"] = user["id"]
                    st.rerun()
                else:
                    st.error("Wrong username or password.")
    with t2:
        with st.form("register"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Full name")
            email = c2.text_input("Email")
            u = c1.text_input("Username")
            utype = c2.selectbox("I am a...", utils.USER_TYPES)
            p1 = c1.text_input("Password", type="password")
            p2 = c2.text_input("Confirm password", type="password")
            if st.form_submit_button("Create account", type="primary"):
                if p1 != p2:
                    st.error("Passwords do not match.")
                else:
                    ok, msg = db.register_user(u, email, p1, name, utype)
                    (st.success if ok else st.error)(msg)


# ============================================================== TRANSACTIONS
def page_transactions(user, df, model):
    uid, sym = user["id"], user["currency"]
    st.title("💳 Transactions")

    st.subheader("Add transaction")
    ttype = st.radio("Type", ["Expense", "Income"], horizontal=True)
    with st.form("add_tx", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        d = c1.date_input("Date", value=date.today())
        amt = c2.number_input("Amount", min_value=0.0, step=1.0)
        cats = (["Auto-detect"] + utils.EXPENSE_CATEGORIES) if ttype == "Expense" else utils.INCOME_CATEGORIES
        cat = c3.selectbox("Category", cats)
        desc = st.text_input("Description (e.g. Starbucks, Monthly salary)")
        if st.form_submit_button("Add", type="primary"):
            if amt <= 0:
                st.error("Amount must be greater than 0.")
            else:
                if cat == "Auto-detect":
                    cat = utils.categorize(model, [desc or "other"])[0]
                db.add_transaction(uid, d, ttype, cat, desc, amt)
                st.toast(f"Added {ttype.lower()} in {cat}")
                st.rerun()

    with st.expander("📥 Import from CSV"):
        st.caption("Columns: date, description, amount. Optional: type (Income/Expense), category.")
        up = st.file_uploader("CSV file", type="csv")
        if up is not None and st.button("Import file"):
            imp = pd.read_csv(up)
            if not {"date", "description", "amount"}.issubset(imp.columns):
                st.error("CSV needs date, description and amount columns.")
            else:
                imp["date"] = pd.to_datetime(imp["date"], errors="coerce")
                imp["amount"] = pd.to_numeric(imp["amount"], errors="coerce").abs()
                imp = imp.dropna(subset=["date", "amount"])
                if "type" not in imp:
                    imp["type"] = "Expense"
                if "category" not in imp:
                    imp["category"] = None
                m = imp["category"].isna() & (imp["type"] == "Expense")
                imp.loc[m, "category"] = utils.categorize(model, imp.loc[m, "description"])
                imp["category"] = imp["category"].fillna("Other income")
                db.bulk_add(uid, imp)
                st.success(f"Imported {len(imp)} transactions.")
                st.rerun()

    st.subheader("History")
    f1, f2, f3 = st.columns(3)
    types = f1.multiselect("Type", ["Expense", "Income"], default=["Expense", "Income"])
    cats = f2.multiselect("Category", sorted(df["category"].unique()))
    q = f3.text_input("Search description")
    view = df[df["type"].isin(types)]
    if cats:
        view = view[view["category"].isin(cats)]
    if q:
        view = view[view["description"].fillna("").str.contains(q, case=False)]
    st.dataframe(view.assign(date=view["date"].dt.date), width="stretch", hide_index=True)

    if not view.empty:
        st.subheader("Edit or delete")
        labels = {int(r.id): f"#{r.id} · {r.date:%Y-%m-%d} · {r.type} · {r.category} · {r.description} · {r.amount:,.2f}"
                  for r in view.head(200).itertuples()}
        tx_id = st.selectbox("Pick a transaction", list(labels), format_func=labels.get)
        row = df[df["id"] == tx_id].iloc[0]
        all_cats = utils.EXPENSE_CATEGORIES + utils.INCOME_CATEGORIES
        with st.form(f"edit_{tx_id}"):
            c1, c2, c3, c4 = st.columns(4)
            e_date = c1.date_input("Date", value=row["date"].date())
            e_type = c2.selectbox("Type", ["Expense", "Income"], index=["Expense", "Income"].index(row["type"]))
            e_cat = c3.selectbox("Category", all_cats,
                                 index=all_cats.index(row["category"]) if row["category"] in all_cats else 0)
            e_amt = c4.number_input("Amount", min_value=0.0, value=float(row["amount"]), step=1.0)
            e_desc = st.text_input("Description", value=row["description"] or "")
            b1, b2, _ = st.columns([1, 1, 4])
            if b1.form_submit_button("Save changes", type="primary"):
                db.update_transaction(tx_id, uid, e_date, e_type, e_cat, e_desc, e_amt)
                st.rerun()
            if b2.form_submit_button("Delete"):
                db.delete_transaction(tx_id, uid)
                st.rerun()


# ================================================================== BUDGETS
def budget_status(uid, df, period):
    budgets = db.get_budgets(uid)
    if budgets.empty:
        return budgets.assign(spent=[], pct=[])
    exp = df[(df["type"] == "Expense") & (df["date"].dt.to_period("M") == period)]
    spent = exp.groupby("category")["amount"].sum()
    budgets["spent"] = budgets["category"].map(spent).fillna(0.0)
    budgets["pct"] = budgets["spent"] / budgets["monthly_limit"]
    return budgets


def page_budgets(user, df):
    uid, sym = user["id"], user["currency"]
    st.title("🎯 Budgets")
    st.caption("Set a monthly spending limit per category. Progress is for the current month.")
    with st.form("set_budget"):
        c1, c2 = st.columns(2)
        cat = c1.selectbox("Category", utils.EXPENSE_CATEGORIES)
        limit = c2.number_input("Monthly limit", min_value=0.0, step=10.0)
        if st.form_submit_button("Save budget", type="primary"):
            if limit > 0:
                db.set_budget(uid, cat, limit)
                st.rerun()
            else:
                st.error("Limit must be greater than 0.")

    bs = budget_status(uid, df, pd.Timestamp.today().to_period("M"))
    if bs.empty:
        st.info("No budgets yet. Add one above.")
        return
    over = bs[bs["pct"] > 1]
    near = bs[(bs["pct"] >= 0.8) & (bs["pct"] <= 1)]
    if len(over):
        st.error("Over budget: " + ", ".join(over["category"]))
    if len(near):
        st.warning("Close to the limit (80%+): " + ", ".join(near["category"]))
    for r in bs.itertuples():
        c1, c2 = st.columns([6, 1])
        icon = "🔴" if r.pct > 1 else "🟠" if r.pct >= 0.8 else "🟢"
        c1.progress(min(r.pct, 1.0), text=f"{icon} {r.category}: {money(r.spent, sym)} of "
                                          f"{money(r.monthly_limit, sym)} ({r.pct:.0%})")
        if c2.button("Remove", key=f"delb_{r.id}"):
            db.delete_budget(r.id, uid)
            st.rerun()


# =================================================================== GOALS
def page_goals(user):
    uid, sym = user["id"], user["currency"]
    st.title("🏆 Financial goals")
    with st.form("new_goal"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Goal name (e.g. New laptop)")
        target = c2.number_input("Target amount", min_value=0.0, step=50.0)
        saved = c1.number_input("Already saved", min_value=0.0, step=10.0)
        has_deadline = c2.checkbox("Set a deadline", value=True)
        deadline = c2.date_input("Deadline", value=date.today() + pd.Timedelta(days=180))
        if st.form_submit_button("Create goal", type="primary"):
            if name and target > 0:
                db.add_goal(uid, name, target, saved, deadline if has_deadline else None)
                st.rerun()
            else:
                st.error("Enter a name and a target above 0.")

    goals = db.get_goals(uid)
    if goals.empty:
        st.info("No goals yet.")
        return
    for g in goals.itertuples():
        pct = min(g.saved_amount / g.target_amount, 1.0)
        done = g.saved_amount >= g.target_amount
        with st.container(border=True):
            st.progress(pct, text=f"{'🎉 ' if done else ''}{g.name}: {money(g.saved_amount, sym)} of "
                                  f"{money(g.target_amount, sym)} ({pct:.0%})")
            if g.deadline and not done:
                days = (pd.Timestamp(g.deadline) - pd.Timestamp.today().normalize()).days
                remaining = g.target_amount - g.saved_amount
                if days > 0:
                    per_month = remaining / max(days / 30.4, 1e-9)
                    st.caption(f"{days} days left · save about {money(per_month, sym)} per month to reach it")
                else:
                    st.caption("⚠️ Deadline passed")
            c1, c2, c3 = st.columns([2, 1, 1])
            add = c1.number_input("Add / withdraw funds", step=10.0, key=f"gamt_{g.id}", label_visibility="collapsed")
            if c2.button("Update savings", key=f"gadd_{g.id}") and add != 0:
                db.add_to_goal(g.id, uid, add)
                st.rerun()
            if c3.button("Delete goal", key=f"gdel_{g.id}"):
                db.delete_goal(g.id, uid)
                st.rerun()


# ============================================================== DASHBOARD
def page_dashboard(user, df):
    uid, sym = user["id"], user["currency"]
    st.title("📊 Dashboard & report")
    if df.empty:
        st.info("No transactions yet. Add some on the Transactions page, or load demo data to explore.")
        if st.button("Load demo data"):
            db.bulk_add(uid, utils.make_demo_transactions(user["user_type"]))
            st.rerun()
        return

    df = df.assign(month=df["date"].dt.to_period("M"))
    cur = pd.Timestamp.today().to_period("M")
    months = sorted(set(df["month"]) | {cur}, reverse=True)
    sel = st.selectbox("Month", [str(m) for m in months])
    period = pd.Period(sel)
    m = df[df["month"] == period]
    p = df[df["month"] == period - 1]

    inc, exp = m.loc[m.type == "Income", "amount"].sum(), m.loc[m.type == "Expense", "amount"].sum()
    p_inc, p_exp = p.loc[p.type == "Income", "amount"].sum(), p.loc[p.type == "Expense", "amount"].sum()
    net = inc - exp
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total income", money(inc, sym), f"{inc - p_inc:+,.0f} vs prev")
    c2.metric("Total expenses", money(exp, sym), f"{exp - p_exp:+,.0f} vs prev", delta_color="inverse")
    c3.metric("Net balance", money(net, sym))
    c4.metric("Savings rate", f"{(net / inc if inc else 0):.0%}")

    left, right = st.columns([3, 2])
    trend = (df.groupby(["month", "type"])["amount"].sum().reset_index().tail(24))
    trend["month"] = trend["month"].astype(str)
    left.plotly_chart(px.bar(trend, x="month", y="amount", color="type", barmode="group",
                             title="Income vs expenses by month",
                             color_discrete_map={"Income": "#2e9e6b", "Expense": "#d9534f"}), width="stretch")
    ex = m[m["type"] == "Expense"]
    if ex.empty:
        right.info("No expenses this month.")
    else:
        right.plotly_chart(px.pie(ex, names="category", values="amount", hole=0.45,
                          title="Expenses by category", color_discrete_sequence=CLASSIC), width="stretch")
        daily = ex.groupby(ex["date"].dt.date)["amount"].sum().reset_index()
        st.plotly_chart(px.bar(daily, x="date", y="amount", title="Daily spending"), width="stretch")

    st.subheader("Budget status")
    bs = budget_status(uid, df, period)
    if bs.empty:
        st.caption("No budgets set. Add some on the Budgets page.")
    for r in bs.itertuples():
        st.progress(min(r.pct, 1.0), text=f"{r.category}: {money(r.spent, sym)} / {money(r.monthly_limit, sym)}")

    goals = db.get_goals(uid)
    if not goals.empty:
        st.subheader("Goals")
        for g in goals.itertuples():
            st.progress(min(g.saved_amount / g.target_amount, 1.0),
                        text=f"{g.name}: {money(g.saved_amount, sym)} / {money(g.target_amount, sym)}")

    st.subheader("Monthly report")
    if ex.empty:
        st.caption("No expenses to report for this month.")
    else:
        top = ex.groupby("category")["amount"].sum().sort_values(ascending=False)
        big = ex.sort_values("amount", ascending=False).iloc[0]
        st.markdown(
            f"- **{sel}**: income {money(inc, sym)}, expenses {money(exp, sym)}, net {money(net, sym)}.\n"
            f"- Biggest category: **{top.index[0]}** ({money(top.iloc[0], sym)}, {top.iloc[0] / exp:.0%} of spending).\n"
            f"- Largest single expense: **{big['description'] or big['category']}** ({money(big['amount'], sym)}).")
    st.download_button("⬇️ Download this month (CSV)",
                       m.drop(columns="month").to_csv(index=False), f"report_{sel}.csv")


# ============================================================== INSIGHTS
def page_insights(user, df):
    sym = user["currency"]
    st.title("🔮 Insights")
    exp = df[df["type"] == "Expense"]
    if exp.empty:
        st.info("Add some expenses first.")
        return
    st.subheader("Next month forecast")
    fc = utils.forecast_next_month(exp)
    if fc.empty:
        st.caption("Need at least one full past month of expenses.")
    else:
        st.metric("Forecast total spending", money(fc.sum(), sym))
        st.plotly_chart(px.bar(fc.reset_index(), x="index", y=0, labels={"index": "Category", "0": "Forecast"}),
                        width="stretch")
        budgets = db.get_budgets(user["id"]).set_index("category")["monthly_limit"]
        risky = [c for c in fc.index if c in budgets.index and fc[c] > budgets[c]]
        if risky:
            st.warning("Forecast exceeds budget for: " + ", ".join(risky))

    st.subheader("Unusual expenses")
    thr = st.slider("Sensitivity (lower = more flagged)", 2.0, 8.0, 3.5, 0.5)
    an = utils.detect_anomalies(exp, thr)
    if an.empty:
        st.success("Nothing unusual found.")
    else:
        st.dataframe(an[["date", "description", "category", "amount", "anomaly_score"]]
                     .assign(date=an["date"].dt.date), width="stretch", hide_index=True)

    st.subheader("Tips")
    inc_m = df[df.type == "Income"].groupby(df["date"].dt.to_period("M"))["amount"].sum()
    exp_m = exp.groupby(exp["date"].dt.to_period("M"))["amount"].sum()
    rate = ((inc_m - exp_m) / inc_m).dropna()
    if len(rate) and rate.mean() < 0.2:
        st.write("• Your average savings rate is below 20%. Try trimming your top spending category.")
    elif len(rate):
        st.write("• Your average savings rate is healthy. Consider putting it toward a goal.")
    top = exp.groupby("category")["amount"].sum().sort_values(ascending=False)
    st.write(f"• You spend the most on **{top.index[0]}**. Setting a budget there has the biggest impact.")


def section_savings_advisor(user, df):
    uid, sym = user["id"], user["currency"]
    st.subheader("💡 What to cut to save more")
    income = utils.forecast_next_income(df)
    if income <= 0:
        st.caption("Add some income transactions to get savings advice.")
        return

    mode = st.radio("Set my savings target by", ["Savings rate", "My goals"], horizontal=True)
    if mode == "Savings rate":
        rate = st.slider("Target savings rate", 5, 50, 20, 5, format="%d%%")
        target = income * rate / 100
    else:
        today, target = pd.Timestamp.today().normalize(), 0.0
        for g in db.get_goals(uid).itertuples():
            remaining = g.target_amount - g.saved_amount
            if remaining > 0 and g.deadline:
                days = (pd.Timestamp(g.deadline) - today).days
                if days > 0:
                    target += remaining / max(days / 30.4, 1)
        if target <= 0:
            st.info("No active goals with a deadline. Create one on the Goals page.")
            return

    plan, s = utils.savings_plan(df, target)
    if plan.empty and s["forecast_expenses"] == 0:
        st.caption("Need at least one full past month of expenses to predict.")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Expected income", money(s["income"], sym))
    c2.metric("Forecast spending", money(s["forecast_expenses"], sym))
    c3.metric("Predicted savings", money(s["predicted_savings"], sym))
    c4.metric("Your target", money(s["target"], sym))

    if s["gap"] <= 0:
        st.success("You are on track. Your predicted savings already meet your target.")
        return
    st.write(f"To reach your target you need to cut about **{money(s['gap'], sym)}** from next month's spending.")
    if not s["reachable"]:
        st.warning(f"Cutting alone can free at most {money(s['achievable'], sym)}. "
                   "Consider a lower target or more income.")

    long = plan.melt("category", ["forecast", "new_budget"], var_name="when", value_name="amount")
    long["when"] = long["when"].map({"forecast": "Forecast", "new_budget": "After cuts"})
    st.plotly_chart(px.bar(long, x="category", y="amount", color="when", barmode="group",
                           labels={"amount": "Amount", "category": "Category", "when": ""}), width="stretch")
    show = plan.assign(forecast=plan["forecast"].round(2), cut=plan["cut"].round(2),
                       new_budget=plan["new_budget"].round(2), cut_pct=plan["cut_pct"].map("{:.0%}".format))
    st.dataframe(show.rename(columns={"category": "Category", "forecast": "Forecast", "cut": "Cut",
                                      "new_budget": "New budget", "cut_pct": "Cut %", "why": "Why"}),
                 hide_index=True, width="stretch")
    st.caption(f"If you follow this plan, predicted savings rise to {money(s['predicted_savings'] + s['achievable'], sym)}.")
    if st.button("Apply as monthly budgets"):
        for r in plan.itertuples():
            db.set_budget(uid, r.category, round(r.new_budget, 2))
        st.success("Budgets updated. See them on the Budgets page.")
        
# ============================================================ TRAIN MODEL
def page_train_model(user, df):
    uid = user["id"]
    st.title("🧠 Train model")
    st.caption("Teach the auto-categorizer using your own transactions, so it learns your merchants.")

    exp = df[df["type"] == "Expense"]
    labeled = exp[(exp["category"] != "Other") & exp["description"].fillna("").str.strip().ne("")]
    has_custom = os.path.exists(utils.model_path(uid))
    c1, c2, c3 = st.columns(3)
    c1.metric("Your labeled expenses", len(labeled))
    c2.metric("Categories", labeled["category"].nunique())
    c3.metric("Model in use", "Custom (yours)" if has_custom else "Default")
    if len(labeled) < 20:
        st.info("Add at least 20 categorized expenses for a realistic score. "
                "Until then the model is tested on built-in sample data only.")

    with st.form("train"):
        a, b = st.columns(2)
        test_size = a.slider("Test split", 0.1, 0.4, 0.2, 0.05)
        C = b.select_slider("Regularization (C)", options=[0.1, 0.5, 1.0, 5.0, 10.0], value=1.0)
        go = st.form_submit_button("Train model", type="primary")
    if go:
        with st.spinner("Training..."):
            model, metrics, report = utils.train_and_evaluate(exp, test_size, C)
            utils.save_categorizer(model, uid)
            get_model.clear()
        st.session_state["train_result"] = (metrics, report)
        st.success("Model trained and saved. New expenses will use it for auto-detect.")

    if "train_result" in st.session_state:
        metrics, report = st.session_state["train_result"]
        st.subheader("Results")
        m1, m2, m3 = st.columns(3)
        m1.metric("Accuracy", f"{metrics['accuracy']:.1%}")
        m2.metric("Macro F1", f"{metrics['macro_f1']:.2f}")
        m3.metric("Train / test rows", f"{metrics['n_train']} / {metrics['n_test']}")
        st.caption(f"Tested on: {metrics['eval_on']}")
        st.plotly_chart(px.bar(report.reset_index(), x="index", y="f1-score",
                               labels={"index": "Category", "f1-score": "F1 score"}, range_y=[0, 1]),
                        width="stretch")
        st.dataframe(report[["precision", "recall", "f1-score", "support"]].round(2), width="stretch")

    st.subheader("Try it")
    text = st.text_input("Type a description (e.g. Starbucks, Grab ride, tuition fee)")
    if text:
        model = get_model(uid)
        proba = model.predict_proba([text])[0]
        top = pd.DataFrame({"Category": model.classes_, "Confidence": proba}).sort_values(
            "Confidence", ascending=False).head(3)
        top["Confidence"] = top["Confidence"].map("{:.0%}".format)
        pred = utils.categorize(model, [text])[0]
        st.write(f"Predicted category: **{pred}**")
        st.dataframe(top, hide_index=True, width="content")

    if has_custom and st.button("Reset to default model"):
        os.remove(utils.model_path(uid))
        get_model.clear()
        st.session_state.pop("train_result", None)
        st.rerun()

# ============================================================== PROFILE
def page_profile(user):
    st.title("👤 Profile")
    with st.form("profile"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Full name", user["full_name"] or "")
        email = c2.text_input("Email", user["email"] or "")
        utype = c1.selectbox("I am a...", utils.USER_TYPES, index=utils.USER_TYPES.index(user["user_type"]))
        cur = c2.selectbox("Currency", utils.CURRENCIES,
                           index=utils.CURRENCIES.index(user["currency"]) if user["currency"] in utils.CURRENCIES else 0)
        if st.form_submit_button("Save profile", type="primary"):
            db.update_profile(user["id"], name, email, utype, cur)
            st.success("Profile updated.")
            st.rerun()
    st.subheader("Change password")
    with st.form("pw"):
        old = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        if st.form_submit_button("Update password"):
            ok, msg = db.change_password(user["id"], old, new)
            (st.success if ok else st.error)(msg)
    with st.expander("Danger zone"):
        sure = st.checkbox("I understand this permanently deletes my account and all data")
        if st.button("Delete my account", disabled=not sure):
            db.delete_user(user["id"])
            st.session_state.clear()
            st.rerun()


# ================================================================== MAIN
uid = st.session_state.get("user_id")
user = db.get_user(uid) if uid else None
if not user:
    st.session_state.pop("user_id", None)
    auth_page()
    st.stop()

PAGES = ["Dashboard", "Transactions", "Budgets", "Goals", "Insights", "Train model", "Profile"]
ICONS = {"Dashboard": "📊", "Transactions": "💳", "Budgets": "🎯", "Goals": "🏆",
         "Insights": "🔮", "Train model": "🧠", "Profile": "👤"}


with st.sidebar:
    st.markdown("<div class='brand'>Expense<span>Tracker</span></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='user-card'><b>{html.escape(user['full_name'] or user['username'])}</b><br>"
                f"<small>{html.escape(user['user_type'])}</small></div>", unsafe_allow_html=True)
    page = st.radio("Menu", PAGES, format_func=lambda p: f"{ICONS[p]}  {p}", label_visibility="collapsed")
    st.divider()
    if st.button("Log out"):
        st.session_state.clear()
        st.rerun()

df = db.get_transactions(user["id"])
if page == "Dashboard":
    page_dashboard(user, df)
elif page == "Transactions":
    page_transactions(user, df, get_model())
elif page == "Budgets":
    page_budgets(user, df)
elif page == "Goals":
    page_goals(user)
elif page == "Insights":
    page_insights(user, df)
elif page == "Train model":
    page_train_model(user, df)
else:
    page_profile(user)
