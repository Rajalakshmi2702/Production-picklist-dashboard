# Production-picklist-dashboard
Streamlit dashboard for visualizing production picklist data with shift, line, and FIFO analytics.

An interactive Streamlit dashboard for analyzing production picklist data from Excel files.
The dashboard helps visualize FIFO counts, picklist activity, shift-wise production, and line-wise material movement using dynamic charts and filters.

Technologies Used:
Python
Streamlit – Interactive dashboard framework
Pandas – Data processing and analysis
Plotly Express – Data visualization
OpenPyXL / XlsxWriter – Excel file handling

Features:
📂 Upload Excel files containing production or operational data
📅 Filter records by single date or custom date range
🏭 Analyze activity across different production lines or workstations
⏱ Automatically classify data based on work shifts
📊 Interactive charts and dashboards powered by Plotly
📦 Track and analyze unique item or batch identifiers across production lines
🔢 Key performance indicators (KPIs) for quick insights, including:
Total unique item count
Category-wise item counts
Overall operational activity metrics

Input File Format
The uploaded Excel file must contain the following columns:
Print Date
Printed By
Pick List
Line
Part Number
Qty.
FIFO
Multiple sheets in the Excel file are supported and will be automatically merged.

Authors:
[Niranjana Sivaram](https://github.com/Niranjanasivaram)
[Mohammed Sulaiman N](https://github.com/sulai11)
[Nikhitha M](https://github.com/Nikhitha0620)
[Rajalakshmi S](https://github.com/Rajalakshmi2702)

