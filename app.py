import streamlit as st
import pandas as pd
from datetime import time
import io
import plotly.express as px

st.set_page_config(page_title="Production Dashboard", layout="wide")
st.title("📊 Production Picklist Dashboard")


# ================= LOAD EXCEL =================
@st.cache_data
def load_excel(uploaded_file):
    excel_file = pd.ExcelFile(uploaded_file)

    dfs = []
    for sheet in excel_file.sheet_names:
        temp = pd.read_excel(uploaded_file, sheet_name=sheet)
        dfs.append(temp)

    return pd.concat(dfs, ignore_index=True)


# ================= LINE NORMALIZER =================
def normalize_line(col):
    return (
        col.astype(str)
        .str.replace(r"[\t\n\r]", "", regex=True)
        .str.replace(r"\s+", "", regex=True)
        .str.strip()
        .str.upper()
    )


# ================= FILE UPLOAD =================
uploaded_file = st.file_uploader("📂 Upload Excel File", type=["xlsx"])

if uploaded_file:

    df = load_excel(uploaded_file)

    # ================= REQUIRED COLUMNS =================
    required_cols = [
        "Print Date",
        "Printed By",
        "Pick List",
        "Line",
        "Part Number",
        "Qty.",
        "FIFO",
    ]

    missing = [c for c in required_cols if c not in df.columns]

    if missing:
        st.error(f"Missing columns: {missing}")
        st.stop()

    # ================= DATETIME CLEAN =================
    df["DateTime"] = pd.to_datetime(df["Print Date"], errors="coerce")

    df["Print Date"] = df["DateTime"].dt.date
    df["Time_clean"] = df["DateTime"].dt.time

    # >>> ADD THIS NEW CLEANUP BLOCK <<<
    # Standardize 'Pick List' to prevent duplicate counts from spaces or mixed types
    df["Pick List"] = df["Pick List"].astype(str).str.strip().str.upper()
    # Remove any rows where Pick List became "NAN" due to empty Excel cells
    df = df[df["Pick List"] != "NAN"]
    # ================= SHIFT LOGIC =================
    def get_shift(t):
        if pd.isna(t):
            return "Unknown"
        if time(0, 0) <= t <= time(7, 15):
            return "A Shift"
        elif time(7, 16) <= t <= time(15, 45):
            return "B Shift"
        elif time(15, 46) <= t <= time(23, 59, 59):
            return "C Shift"
        return "Unknown"

    df["Shift"] = df["Time_clean"].apply(get_shift)

    df["Shift_Order"] = df["Shift"].map({
        "A Shift": 1,
        "B Shift": 2,
        "C Shift": 3
    })

    # ================= CLEAN LINE =================
    @st.cache_data
    def clean_line(col):
        return normalize_line(col)

    df["Line"] = clean_line(df["Line"])

    # ================= BASE LINE =================
    import re

    def extract_base_line(line):

        line = str(line).upper().replace(" ", "")

        # SMT format
        smt = re.search(r"SMT0*(\d+)", line)
        if smt:
            return f"SMT{smt.group(1)}"

        # LINE format  (IMPORTANT NEW)
        line_match = re.search(r"LINE0*(\d+)", line)
        if line_match:
            return f"SMT{line_match.group(1)}"

        return line

    df["Base_Line"] = df["Line"].apply(extract_base_line)

    # ================= EXTRA NORMALIZATION HELPERS =================
    def normalize_text(x):
        return str(x).upper().replace(" ", "").replace("-", "")

    # ================= SPECIAL TAGGING =================
    def tag_special_lines(row):
        line_raw = str(row["Line"])
        line_clean = normalize_text(line_raw)

        # LEAD CUTTING → SMT5
        if "LEADCUTTING" in line_clean:
            return "SMT5"

        # SOLDER PASTE POU → separate
        if "SOLDERPASTEPOU" in line_clean:
            return "SOLDER_PASTE_POU"

        # OFFLINE GROUP
        if (
            "MSL" in line_clean
            or "OFFLINEPOU01" in line_clean
            or "OFFLINEBAREPCB" in line_clean
        ):
            return "OFFLINE"

        return None

    df["Special_Tag"] = df.apply(tag_special_lines, axis=1)

    # ================= PARENT LINE =================
    df["Parent_Line"] = df["Base_Line"]

    # Apply overrides
    df.loc[df["Special_Tag"] == "SMT5", "Parent_Line"] = "SMT5"
    df.loc[df["Special_Tag"] == "SOLDER_PASTE_POU", "Parent_Line"] = "SOLDER_PASTE_POU"
    df.loc[df["Special_Tag"] == "OFFLINE", "Parent_Line"] = "OFFLINE"

    # Non SMT → OTHERS (excluding special ones)
    df.loc[
        (~df["Parent_Line"].str.startswith("SMT")) &
        (~df["Parent_Line"].isin(["SOLDER_PASTE_POU","OFFLINE"])),
        "Parent_Line"
    ] = "OTHERS"
    
    # ================= PARENT LINE =================
    df["Parent_Line"] = df["Base_Line"]

    # Non SMT lines → group as OTHERS
    df.loc[
        ~df["Base_Line"].str.startswith("SMT"),
        "Parent_Line"
    ] = "OTHERS"

    # ================= UNIQUE PRODUCT =================
    df["Product_FIFO"] = df["Part Number"].astype(str).str.cat(
        df["FIFO"].astype(str), sep="_"
    )

    # ================= BUILD LINE OPTIONS =================
    df["Line"] = df["Line"].str.upper()

    smt_lines = df[df["Base_Line"].str.startswith("SMT")]
    other_lines = df[~df["Base_Line"].str.startswith("SMT")]

    grouped_line_options = []
    display_to_actual = {}

    if not smt_lines.empty:

        smt_lines["Base_Line"] = smt_lines["Line"].apply(extract_base_line)
        base_lines = sorted(smt_lines["Base_Line"].unique())

        for base in base_lines:

            all_option = f"{base} (ALL)"
            grouped_line_options.append(all_option)
            display_to_actual[all_option] = ("BASE", base)

            sub_lines = sorted(
                smt_lines[smt_lines["Base_Line"] == base]["Line"].unique()
            )

            for sub in sub_lines:
                grouped_line_options.append(sub)
                display_to_actual[sub] = ("LINE", sub)

    if not other_lines.empty:

        grouped_line_options.append("OTHER LINES (ALL)")
        display_to_actual["OTHER LINES (ALL)"] = ("OTHER", "ALL")

        for line in sorted(other_lines["Line"].unique()):
            grouped_line_options.append(line)
            display_to_actual[line] = ("LINE", line)

    # ================= SIDEBAR =================
    st.sidebar.header("🔎 Filters")

    mode = st.sidebar.radio("📅 Mode", ["Single Date", "Date Range"])

    min_date = df["Print Date"].min()
    max_date = df["Print Date"].max()

    if mode == "Single Date":
        selected_date = st.sidebar.date_input(
            "Select Date",
            min_value=min_date,
            max_value=max_date,
            value=min_date
        )
    else:
        selected_dates = st.sidebar.date_input(
            "Select Date Range",
            min_value=min_date,
            max_value=max_date,
            value=(min_date, max_date)
        )

    apply = st.sidebar.button("Apply Filter")

    # ================= FILTER =================
    if apply:

        if mode == "Single Date":
            filtered = df[df["Print Date"] == selected_date]
        else:
            # Handle the Streamlit edge case where a user hasn't selected the end date yet
            if len(selected_dates) == 2:
                start, end = selected_dates
                filtered = df[
                    (df["Print Date"] >= start) &
                    (df["Print Date"] <= end)
                ]
            else:
                start = selected_dates[0]
                filtered = df[df["Print Date"] == start]
  
        
        # ================= KPI DATA (FROM GRAPH 5 LOGIC) =================

        kpi_df = filtered.copy()

        import re

        def classify_material(line):
            line = str(line).upper().replace(" ", "")

            if re.search(r"POU0*3$", line) or re.search(r"POU0*4$", line):
                return "TH/barePCB"
            return "Reels"

        kpi_df["Type"] = kpi_df["Line"].apply(classify_material)

        # Only SMT lines (same as Graph 5)
        kpi_df = kpi_df[kpi_df["Parent_Line"].str.startswith("SMT")]

        # Calculations
        total_fifo = kpi_df["FIFO"].nunique()
        reels_count = kpi_df[kpi_df["Type"] == "Reels"]["FIFO"].nunique()
        th_count = kpi_df[kpi_df["Type"] == "TH/barePCB"]["FIFO"].nunique()
        # Picklist count matching Graph 4 logic
        # ================= SUMMARY =================

        st.subheader("📊 Summary")

        # Picklist count matching Graph 4
        picklist_df = filtered[filtered["Parent_Line"] != "OTHERS"]
        total_picklist = picklist_df["Pick List"].nunique()

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("📋 Total Picklist Count", total_picklist)
        c2.metric("🔢 Total FIFO Count", total_fifo)
        c3.metric("🧵 Reels Count", reels_count)
        c4.metric("📦 TH / BarePCB Count", th_count)
        
        # ================= SORT =================
        filtered_sorted = filtered.sort_values(
            by=["Print Date", "Shift_Order", "Time_clean"]
        )

        download_df = filtered_sorted.drop(columns=["Product_FIFO", "Shift_Order"])

        # ================= GRAPH DASHBOARD =================
        r2c1,r2c2 = st.columns(2)

        # ⭐ GRAPH 1
        with r2c1:

            st.subheader("FIFO Count by Line & Shift")

            order_lines = [
                "SMT1","SMT2","SMT3","SMT4","SMT5","SMT6",
                "SOLDER_PASTE_POU",
                "OFFLINE"
            ]

            shift_order = ["A Shift","B Shift","C Shift"]

            full_index = pd.MultiIndex.from_product(
                [order_lines, shift_order],
                names=["Parent_Line","Shift"]
            )

            # VERIFIED: Correctly uses "FIFO"
            g1 = (
                filtered.groupby(["Parent_Line","Shift"])["FIFO"]
                .nunique()
                .reindex(full_index, fill_value=0)
                .reset_index(name="Count")
            )

            fig1 = px.bar(
                g1,
                x="Parent_Line",
                y="Count",
                color="Shift",
                barmode="group",
                text="Count",
                category_orders={
                    "Parent_Line": order_lines,
                    "Shift": shift_order
                },
                color_discrete_map={
                    "A Shift": "#6C8AE4",
                "B Shift": "#F4A261",
                "C Shift": "#2A9D8F"
                }
            )

            fig1.update_traces(textposition="outside")

            fig1.update_layout(
                xaxis_tickangle=-45,
                height=450,
                template="plotly_white"
            )

            st.plotly_chart(fig1,use_container_width=True)

        # ⭐ GRAPH 2
        with r2c2:

            st.subheader("FIFO Count by Date & Shift")

            if filtered.empty:
                st.warning("No data for selected filter")

            else:

                # FULL DATE RANGE
                all_dates = pd.date_range(
                    start=filtered["Print Date"].min(),
                    end=filtered["Print Date"].max()
                )

                all_shifts = ["A Shift","B Shift","C Shift"]

                full_index = pd.MultiIndex.from_product(
                    [all_dates, all_shifts],
                    names=["Print Date","Shift"]
                )

                # VERIFIED: Correctly uses "FIFO"
                g2 = (
                    filtered[filtered["Parent_Line"] != "OTHERS"]
                    .assign(**{
                        "Print Date": pd.to_datetime(filtered["Print Date"])
                    })
                    .groupby(["Print Date","Shift"])["FIFO"]
                    .nunique()
                    .reindex(full_index, fill_value=0)
                    .reset_index(name="Count")
                )

                # ⭐ FORMAT DAY MONTH like 2 FEB
                g2["Axis_Label"] = (
                    g2["Print Date"].dt.day.astype(str)
                    + " "
                    + g2["Print Date"].dt.strftime("%b").str.upper()
                )

                axis_order = (
                    g2.sort_values("Print Date")["Axis_Label"]
                    .drop_duplicates()
                    .tolist()
                )

                fig2 = px.bar(
                    g2,
                    x="Axis_Label",
                    y="Count",
                    color="Shift",
                    barmode="group",
                    text="Count",
                    category_orders={
                        "Axis_Label": axis_order,
                        "Shift": ["A Shift","B Shift","C Shift"]
                    },
                    color_discrete_map={
                        "A Shift": "#6C8AE4",
                "B Shift": "#F4A261",
                "C Shift": "#2A9D8F"
                    }
                )

                fig2.update_traces(textposition="outside")

                fig2.update_layout(
                    xaxis_tickangle=-45,
                    height=450,
                    template="plotly_white"
                )

                st.plotly_chart(fig2,use_container_width=True)

        # -------- BOTTOM LEFT & RIGHT NEW CHARTS --------
        row2_col1, row2_col2 = st.columns(2)

        color_map = {
            "A Shift": "#005F73",
    "B Shift": "#EE9B00",
    "C Shift": "#0A9396"
        }

        shift_order = ["A Shift", "B Shift", "C Shift"]

        # ================= GRAPH 3 (LEFT GRAPH) =================
        with row2_col1:
            st.subheader("📊 Picklist Count by Lines")

            line_order = [ "SMT1","SMT2","SMT3","SMT4","SMT5","SMT6",
                "SOLDER_PASTE_POU",
                "OFFLINE"
                ]
            shift_order = ["A Shift", "B Shift", "C Shift"]

            # Create MultiIndex to ensure every line/shift combo exists (even if 0)
            full_index_lines = pd.MultiIndex.from_product(
                [line_order, shift_order],
                names=["Parent_Line", "Shift"]
            )

            parent_shift = (
                filtered.groupby(["Parent_Line", "Shift"])["Pick List"]
                .nunique()
                .reindex(full_index_lines, fill_value=0)
                .reset_index(name="Count")
            )

            fig3 = px.bar(
                parent_shift,
                x="Parent_Line",
                y="Count",
                color="Shift",
                barmode="group",
                text="Count",
                category_orders={"Shift": shift_order, "Parent_Line": line_order},
                color_discrete_map=color_map
            )
            fig3.update_layout(xaxis_title="Production Line", yaxis_title="Picklists per Line", height=420, template="plotly_white")
            fig3.update_traces(textposition="outside")
            st.plotly_chart(fig3, use_container_width=True)


        # ================= GRAPH 4 (RIGHT GRAPH) =================
        with row2_col2:
            st.subheader("📅 Picklist Count by Date")

            if filtered.empty:
                st.warning("No data available")
            else:
                filtered2 = filtered[filtered["Parent_Line"] != "OTHERS"].copy()
                filtered2["Print Date"] = pd.to_datetime(filtered2["Print Date"])
                filtered2["Axis_Label"] = filtered2["Print Date"].dt.day.astype(str) + "<br>" + filtered2["Print Date"].dt.strftime("%b").str.upper()

                axis_order = filtered2.sort_values("Print Date")["Axis_Label"].drop_duplicates().tolist()
                
                # MultiIndex for Date Graph
                full_index_date = pd.MultiIndex.from_product(
                    [axis_order, shift_order],
                    names=["Axis_Label", "Shift"]
                )

                date_shift = (
                    filtered2.groupby(["Axis_Label", "Shift"])["Pick List"]
                    .nunique()
                    .reindex(full_index_date, fill_value=0)
                    .reset_index(name="Count")
                )

                fig4 = px.bar(
                    date_shift,
                    x="Axis_Label",
                    y="Count",
                    color="Shift",
                    barmode="group",
                    text="Count",
                    category_orders={"Axis_Label": axis_order, "Shift": shift_order},
                    color_discrete_map=color_map
                )
                fig4.update_layout(xaxis_title="Day / Month", yaxis_title="Total Unique Picklists", height=420, template="plotly_white")
                fig4.update_traces(textposition="outside")
                st.plotly_chart(fig4, use_container_width=True)

        # ================= GRAPH 5 DATA PREP =================

        g5_df = filtered.copy()

        # classify Type
        g5_df["Type"] = "Reels"

        import re

        def classify_material(line):

            raw = str(line)
            clean = raw.upper().replace(" ", "").replace("-", "")

            # SOLDER PASTE → TH
            if "SOLDERPASTEPOU" in clean:
                return "TH/barePCB"

            # POU3 / POU4 → TH
            if re.search(r"POU0*3$", clean) or re.search(r"POU0*4$", clean):
                return "TH/barePCB"

            # LEAD CUTTING → REELS
            if "LEADCUTTING" in clean:
                return "Reels"

            return "Reels"


        g5_df["Type"] = g5_df["Line"].apply(classify_material)

        # only SMT lines
        g5_df = g5_df[g5_df["Parent_Line"].str.startswith("SMT")]

        order_lines = ["SMT1","SMT2","SMT3","SMT4","SMT5","SMT6"]
        type_order = ["Reels","TH/barePCB"]

        full_index = pd.MultiIndex.from_product(
            [order_lines, type_order],
            names=["Parent_Line","Type"]
        )

        # VERIFIED: Correctly uses "FIFO"
        g5 = (
            g5_df.groupby(["Parent_Line","Type"])["FIFO"]
            .nunique()
            .reindex(full_index, fill_value=0)
            .reset_index(name="Count")
        )

        # ================= GRAPH 5 =================

        st.subheader("📦 FIFO Count by SMT Line vs Material Type")

        fig5 = px.bar(
            g5,
            x="Parent_Line",
            y="Count",
            color="Type",
            barmode="group",
            text="Count",
            category_orders={
                "Parent_Line": order_lines,
                "Type": type_order
            },
            color_discrete_map={
                "Reels": "#1f77b4",
                "TH/barePCB": "#ff7f0e"
            }
        )

        fig5.update_traces(textposition="outside")

        fig5.update_layout(
            xaxis_title="SMT Line",
            yaxis_title="Unique FIFO Count",
            height=450,
            template="plotly_white"
        )

        st.plotly_chart(fig5, use_container_width=True)

        # ================= EXPORT =================
        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:

            download_df.to_excel(writer, index=False, sheet_name="Data")

            workbook = writer.book
            worksheet = writer.sheets["Data"]

            for i, col in enumerate(download_df.columns):
                column_data = download_df[col].astype(str)
            
                if column_data.empty:
                    max_len = len(col)
                else:
                    max_len = column_data.str.len().max()

    column_len = max(max_len, len(col)) + 2
    worksheet.set_column(i, i, column_len)

        st.download_button(
            "📥 Download Filtered Excel",
            data=buffer.getvalue(),
            file_name="filtered_picklist.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
