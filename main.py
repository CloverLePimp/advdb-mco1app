import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine
import streamlit.components.v1 as components

# Establish a connection to the MySQL database using SQLAlchemy
engine = create_engine("mysql+pymysql://root:12345@127.0.0.1:3306/sys")

# Streamlit App - Page Config
st.set_page_config(page_title='Steam OLAP Dashboard', page_icon=':bar_chart:', layout='wide')

# Custom CSS for better styling
st.markdown("""
    <style>
    .sidebar .sidebar-content {
        background-color: #f8f9fa;
        color: #333;
    }
    .css-1v3fvcr {
        cursor: pointer;
    }
    .css-1v3fvcr:hover {
        background-color: #e1e1e1;
    }
    .stButton>button {
        background-color: #007bff;
        color: #ffffff;
        border-radius: 8px;
        border: none;
        padding: 10px;
        font-size: 16px;
    }
    .stButton>button:hover {
        background-color: #0056b3;
    }
    .report-title {
        font-size: 2rem;
        color: #007bff;
        text-align: center;
        margin-top: 1rem;
        margin-bottom: 2rem;
    }
    .main-container {
        background-color: #f0f2f6;
        padding: 2rem;
        border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)

# Streamlit App
st.markdown('<div class="main-container">', unsafe_allow_html=True)

st.title('📊 Steam OLAP Dashboard')

# Sidebar for selecting different reports
st.sidebar.header('Filter Reports')
report = st.sidebar.radio(
    "Select a Report:",
    ("Roll-Up: Total Player Count by Genre", "Drill-Down: Average Playtime by Year and Genre", "Dice: Games Released by Date and Genre", "Slice: High-Performing Games by Price", "Pivot: Average Playtime by Genre")
)

if report == "Roll-Up: Total Player Count by Genre":
    st.markdown('<h2 class="report-title">Roll-Up: Total Player Count by Genre</h2>', unsafe_allow_html=True)
    rollup_query = """
        SELECT 
            ai.Genres, 
            SUM(a.peak_ccu) AS total_peak_users
        FROM 
            app a
        JOIN 
            app_info ai ON a.info_id = ai.info_id
        GROUP BY 
            ai.Genres;
    """
    rollup_df = pd.read_sql(rollup_query, con=engine)
    rollup_df['Genres'] = rollup_df['Genres'].str.split(',')
    rollup_df = rollup_df.explode('Genres')
    rollup_agg_df = rollup_df.groupby('Genres', as_index=False).sum()
    # Aggregate small genres into 'Others'
    total_peak_users_sum = rollup_agg_df['total_peak_users'].sum()
    rollup_agg_df['percentage'] = (rollup_agg_df['total_peak_users'] / total_peak_users_sum) * 100
    others_df = rollup_agg_df[rollup_agg_df['percentage'] < 5].copy()
    rollup_agg_df = rollup_agg_df[rollup_agg_df['percentage'] >= 5]
    if not others_df.empty:
        others_total = others_df['total_peak_users'].sum()
        rollup_agg_df = pd.concat([rollup_agg_df, pd.DataFrame({'Genres': ['Others'], 'total_peak_users': [others_total]})], ignore_index=True)
    fig = px.pie(rollup_agg_df, names='Genres', values='total_peak_users', title='Total Player Count by Genre', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
    fig.update_layout(title_font_size=24, title_x=0.5, legend_title='Genres')
    st.plotly_chart(fig, use_container_width=True)

elif report == "Drill-Down: Average Playtime by Year and Genre":
    st.markdown('<h2 class="report-title">Drill-Down: Average Playtime by Year and Genre</h2>', unsafe_allow_html=True)
    genres = ['Action', 'Adventure', 'RPG', 'Simulation', 'Strategy', 'Sports']
    drilldown_data = []
    for genre in genres:
        drilldown_query = f"""
            SELECT 
                AVG(a.average_playtime_twoweeks) AS average_playtime, 
                '{genre}' AS genre, 
                YEAR(STR_TO_DATE(ai.release_date, '%%b %%d, %%Y')) AS release_year
            FROM 
                app_info ai
            JOIN 
                app a ON a.info_id = ai.info_id
            WHERE 
                ai.Genres LIKE '%%{genre}%%'
                AND a.average_playtime_twoweeks > 0
                AND a.average_playtime_forever > 0
            GROUP BY 
                release_year
            ORDER BY 
                release_year;
        """
        drilldown_df = pd.read_sql(drilldown_query, con=engine)
        drilldown_data.append(drilldown_df)
    drilldown_df_combined = pd.concat(drilldown_data, ignore_index=True)
    drilldown_df_combined = drilldown_df_combined.sort_values(by='release_year')

    # Smoothing the average playtime data using a rolling average
    drilldown_df_combined['average_playtime_smoothed'] = drilldown_df_combined.groupby('genre')['average_playtime'].transform(lambda x: x.rolling(window=2, min_periods=1).mean())

    # Create the updated line chart with enhanced visualization
    fig = px.line(drilldown_df_combined, x='release_year', y='average_playtime_smoothed', color='genre',
                  title='Average Playtime (Last Two Weeks) by Year and Genre', markers=True)
    fig.update_traces(marker=dict(size=8, symbol='circle'))
    fig.update_layout(
        title_font_size=24,
        title_x=0.5,
        xaxis_title='Release Year',
        yaxis_title='Average Playtime (Hours)',
        colorway=px.colors.qualitative.Set1,
        xaxis=dict(showgrid=True, zeroline=False),
        yaxis=dict(showgrid=True, zeroline=False, range=[0, 2000]),
        legend_title='Genre'
    )
    st.plotly_chart(fig, use_container_width=True)

elif report == "Dice: Games Released by Date and Genre":
    st.markdown('<h2 class="report-title">Dice: Number of Games per Genre Given Minimum User Score</h2>', unsafe_allow_html=True)
    # Sidebar filters for start date, end date, and user score selection
    start_year, end_year = st.sidebar.slider('Select Release Year Range', min_value=2000, max_value=2025, value=(2010, 2025))
    min_score, max_score = st.sidebar.slider('Select User Score Range', min_value=0, max_value=100, value=(1, 100))

    # Construct SQL query with user input
    dice_query = f"""
        WITH RECURSIVE NumberSeries AS (
            SELECT 1 AS num
            UNION ALL
            SELECT num + 1
            FROM NumberSeries
            WHERE num <= 19 
        )
        SELECT 
            SUBSTRING_INDEX(SUBSTRING_INDEX(ai.Genres, ',', NumberSeries.num), ',', -1) AS genre, 
            COUNT(*) AS count
        FROM app_info ai
        JOIN app a ON a.info_id = ai.info_id
        JOIN NumberSeries ON NumberSeries.num <= (LENGTH(ai.Genres) - LENGTH(REPLACE(ai.Genres, ',', '')) + 1)
        WHERE a.user_score BETWEEN {min_score} AND {max_score}
          AND YEAR(STR_TO_DATE(ai.release_date, '%%b %%d, %%Y')) BETWEEN {start_year} AND {end_year}
          AND SUBSTRING_INDEX(SUBSTRING_INDEX(ai.Genres, ',', NumberSeries.num), ',', -1) IS NOT NULL
        GROUP BY genre
        ORDER BY count DESC;
    """

    dice_df = pd.read_sql(dice_query, con=engine)

    # Create the bar plot with genres as categories and number of games as values
    fig = px.bar(dice_df, x='genre', y='count', color='genre', title='Number of Games per Genre Given Minimum User Score', labels={'count': 'Number of Games', 'genre': 'Genre'})
    fig.update_layout(title_font_size=24, title_x=0.5, xaxis_title='Genre', yaxis_title='Number of Games', colorway=px.colors.qualitative.Set2)
    st.plotly_chart(fig, use_container_width=True)

elif report == "Slice: High-Performing Games by Price":
    st.markdown('<h2 class="report-title">Slice: High-Performing Games by Price</h2>', unsafe_allow_html=True)
    # Slider for selecting price range
    price_range = st.sidebar.slider('Select Price Range', min_value=0, max_value=200, value=(0, 50))

    slice_query = f"""
        SELECT 
            ai.Genres, 
            AVG(a.positive_reviews) AS avg_positive_reviews, 
            AVG(a.negative_reviews) AS avg_negative_reviews
        FROM 
            app a
        JOIN 
            app_info ai ON a.info_id = ai.info_id
        WHERE 
            ai.Price BETWEEN {price_range[0]} AND {price_range[1]}
            AND a.positive_reviews > 0
            AND a.negative_reviews > 0
        GROUP BY 
            ai.Genres
        ORDER BY 
            avg_positive_reviews DESC;
    """
    slice_df = pd.read_sql(slice_query, con=engine)
    slice_df['Genres'] = slice_df['Genres'].str.split(',')
    slice_df = slice_df.explode('Genres')
    slice_df = slice_df.drop_duplicates(subset=['Genres'])
    fig = px.bar(slice_df, x='Genres', y=['avg_positive_reviews', 'avg_negative_reviews'], barmode='group', title='Average Positive and Negative Reviews by Genre', labels={'value': 'Average Count', 'Genres': 'Genre'})
    fig.update_layout(title_font_size=24, title_x=0.5, xaxis_title='Genre', yaxis_title='Average Review Count', colorway=px.colors.qualitative.Set1)
    st.plotly_chart(fig, use_container_width=True)

elif report == "Pivot: Average Playtime by Genre":
    st.markdown('<h2 class="report-title">Pivot: Average Playtime by Genre</h2>', unsafe_allow_html=True)
    pivot_query = """
        SELECT 
            ai.Genres, 
            AVG(a.average_playtime_forever) AS avg_playtime_forever, 
            AVG(a.average_playtime_twoweeks) AS avg_playtime_recent
        FROM 
            app a
        JOIN 
            app_info ai ON a.info_id = ai.info_id
        WHERE 
            a.average_playtime_forever > 0
            AND a.average_playtime_twoweeks > 0
        GROUP BY 
            ai.Genres;
    """
    pivot_df = pd.read_sql(pivot_query, con=engine)
    pivot_df['Genres'] = pivot_df['Genres'].str.split(',')
    pivot_df = pivot_df.explode('Genres')
    pivot_agg_df = pivot_df.groupby('Genres', as_index=False).mean()

    # Create a horizontal bar plot similar to the provided example
    fig = px.bar(pivot_agg_df, y='Genres', x=['avg_playtime_forever', 'avg_playtime_recent'], title='Average Playtime by Genre', barmode='overlay', orientation='h', labels={'value': 'Average Playtime (Hours)', 'Genres': 'Genre'})
    fig.update_traces(marker=dict(line=dict(width=1)), width=0.8)
    fig.update_traces(marker_color=['#B0B0B0'], selector=dict(name='avg_playtime_forever'))
    fig.update_traces(marker_color=['#404040'], selector=dict(name='avg_playtime_recent'))
    fig.update_layout(title_font_size=24, title_x=0.5, yaxis_title='Genre', xaxis_title='Average Playtime (Hours)', plot_bgcolor='#f0f2f6', colorway=['#B0B0B0', '#404040'], height=700, width=1000)
    st.plotly_chart(fig, use_container_width=False)

# Close the database connection
engine.dispose()

st.markdown('</div>', unsafe_allow_html=True)
