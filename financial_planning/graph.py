from datetime import date as Date
from matplotlib import dates as mpl_dates, pyplot, ticker


def plot(title: str, dates: list[Date], y_data: dict[str, list[float] | list[float]]):
    # for category, category_values in y_data.items():
    # the figure that will contain the plot
    fig = pyplot.figure()
    fig.set_figwidth(10)
    fig.set_figheight(3)
    ax = fig.gca()  # get the current axes
    # Text in the x-axis will be displayed in 'YYYY-mm' format.
    ax.xaxis.set_major_formatter(mpl_dates.DateFormatter('%Y-%b'))
    ax.yaxis.set_major_formatter(ticker.StrMethodFormatter('${x:,.0f}'))

    ax.set_title(title)
    ax.grid(True)
    ax.axhline(y=0, color='black', linewidth=0.75)
    # Rotates and right-aligns the x labels so they don't crowd each other.
    for label in ax.get_xticklabels(which='major'):
        label.set(rotation=30, horizontalalignment='right')

    # print(y_data)
    if isinstance(y_data, dict):
        for name, data in y_data.items():
            ax.plot(dates, data, label=name)
            ax.legend()
    else:
        ax.plot(dates, y_data)
