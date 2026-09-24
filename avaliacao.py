from io import StringIO
from pathlib import Path
from tempfile import gettempdir
from zipfile import ZipFile

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator
import pandas as pd
import requests

STATES = ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO']

GEOGRAPHIES = STATES+['ZZ']
MAIN_STATES = ['SP','MG','RJ','BA','PR']
COLORS      = ['#173F66','#B13B42','#245C48','#477EAB','#83A9C4','#909AA3','#796C65']
STATE_COLORS = dict(zip(MAIN_STATES,['#477EAB','#B13B42','#245C48','#E1B45C','#80609A']))

plt.rcParams.update({
    'axes.prop_cycle':plt.cycler(color=COLORS),
    'axes.grid':True,
    'axes.grid.axis':'both',
    'axes.axisbelow':True,
    'grid.color':'#DCE2E7',
    'grid.linewidth':0.7,
    'axes.spines.top':False,
    'axes.spines.right':False,
    'axes.edgecolor':'#AAB4BE',
    'font.size':11,
    'legend.frameon':False,
    'lines.linewidth':2,
    'figure.facecolor':'white'
})

SELECTED_INSTITUTES = ['MDA','Quaest','Datafolha','AtlasIntel/Internet','Paraná Pesquisas','FSB','PoderData','Ideia Big Data','Ipec','Real Time Big Data','Futura']

ELECTIONS = {
    2002: {'first_round':'2002-10-06','date':'2002-10-27','candidates':{13:'Lula',45:'Serra'}},
    2006: {'first_round':'2006-10-01','date':'2006-10-29','candidates':{13:'Lula',45:'Alckmin'}},
    2010: {'first_round':'2010-10-03','date':'2010-10-31','candidates':{13:'Dilma',45:'Serra'}},
    2014: {'first_round':'2014-10-05','date':'2014-10-26','candidates':{13:'Dilma',45:'Aécio'}},
    2018: {'first_round':'2018-10-07','date':'2018-10-28','candidates':{13:'Haddad',17:'Bolsonaro'}},
    2022: {'first_round':'2022-10-02','date':'2022-10-30','candidates':{13:'Lula',22:'Bolsonaro'}},
    2026: {'first_round':'2026-10-04','date':'2026-10-25','start':'2026-01-01',
           'candidates':{13:'Lula',22:'Flávio Bolsonaro'},'completed':False}
}


def election_settings(year):
    """Return candidate names and the daily calendar for a completed runoff."""
    if year not in ELECTIONS:
        raise ValueError(f'Supported completed runoff years: {list(ELECTIONS)}')
    candidates = list(ELECTIONS[year]['candidates'].values())
    dates      = pd.date_range(start=f'{year}-09-01',end=ELECTIONS[year]['date'])
    return candidates, dates


def mark_election_dates(fig,year):
    """Mark the selected election's configured first round and runoff on each axis."""
    first_round = pd.Timestamp(ELECTIONS[year]['first_round'])
    runoff      = pd.Timestamp(ELECTIONS[year]['date'])
    for ax in fig.axes:
        for date,label in [(first_round,'First round'),(runoff,'Runoff')]:
            ax.axvline(date,color='#606970',linestyle='--',linewidth=1.2)
            ax.annotate(label,
                        xy=(date,0.03),
                        xycoords=('data','axes fraction'),
                        xytext=(-4,0),
                        textcoords='offset points',
                        rotation=90,
                        ha='right',
                        va='bottom',
                        color='#444C53',
                        fontsize=10)


def import_prepared_data(year=2022,source='data/data.csv',institutes=SELECTED_INSTITUTES,show=True):
    """Prepare national and state head-to-head polls for an election.

    Parameters
    ----------
    year : int
        Completed runoff year in ELECTIONS.
    source : str or path-like
        Poll CSV with the original data.csv schema.
    institutes : list of str, optional
        Pollsters to retain. None retains all pollsters in the source.
    show : bool
        Print unique-survey counts and weekly national counts.

    Returns
    -------
    tuple
        National poll DataFrame and dictionary of state poll DataFrames.
        Each survey is normalized to two-candidate shares. All earlier polls
        from the election year are retained for the initial ten-poll average.
    """
    candidates, dates = election_settings(year)
    # The CSV mixes historical UTF-8 rows with Windows-1252 additions.
    lines = []
    for line in Path(source).read_bytes().splitlines(keepends=True):
        try:
            lines.append(line.decode('utf-8'))
        except UnicodeDecodeError:
            lines.append(line.decode('cp1252'))
    data = pd.read_csv(StringIO(''.join(lines)))

    data['data']           = pd.to_datetime(data['data']).dt.normalize()
    data['tipo']           = data['tipo'].str.normalize('NFC')
    data['nome_candidato'] = data['nome_candidato'].replace({'Fernando Haddad':'Haddad','Dilma Rousseff':'Dilma','Aécio Neves':'Aécio'})
    data['sigla_uf']       = data['sigla_uf'].fillna('BR')
    data = data.loc[(data['ano']==year) 
                    & (data['cargo']=='presidente') 
                    & (data['turno']==2)
                    & data['tipo'].isin(['estimulada','espontânea'])
                    & data['nome_candidato'].isin(candidates)
                    & data['data'].le(dates[-1])]
    if institutes is not None:
        data = data.loc[data['instituto'].isin(institutes)]
    if data.empty:
        raise ValueError(f'No eligible runoff polls for {year} in {source}.')

    keys  = ['data','sigla_uf','ano','instituto','id_pesquisa']
    polls = data.pivot_table(index=keys,columns='nome_candidato',values='percentual')
    polls = polls.reindex(columns=candidates).dropna()
    polls = polls.loc[polls.sum(axis=1)>0]
    polls = polls.div(polls.sum(axis=1),axis=0).reset_index().sort_values('data',kind='stable')
    if polls.empty:
        raise ValueError(f'No complete two-candidate runoff scenarios for {year}.')

    polls.columns.name = None
    nacional = polls.loc[polls['sigla_uf']=='BR'].reset_index(drop=True)
    estadual = {uf:frame.reset_index(drop=True) for uf,frame in polls.loc[polls['sigla_uf'].isin(GEOGRAPHIES)].groupby('sigla_uf')}
    if show:
        selected = polls.loc[polls['data'].between(dates[0],dates[-1])]
        counts   = selected.groupby('sigla_uf')['id_pesquisa'].nunique().reindex(['BR']+GEOGRAPHIES,fill_value=0)
        print(f'\nTracking period: {dates[0]:%d %b %Y} to {dates[-1]:%d %b %Y}')
        print(f'National surveys: {counts.loc["BR"]}; states with polls (including DF): {(counts.loc[STATES]>0).sum()}')
        print(counts.loc[GEOGRAPHIES].rename('surveys').to_string())
        selected = nacional.loc[nacional['data'].between(dates[0],dates[-1])]
        weeks    = pd.period_range(dates[0],dates[-1],freq='W-SUN')
        weekly   = selected.groupby(selected['data'].dt.to_period('W-SUN'))['id_pesquisa'].nunique().reindex(weeks,fill_value=0)
        print('\nNational surveys by week (Monday-Sunday; boundary weeks clipped to tracking period):')
        print(weekly.to_string())
    return nacional, estadual


def aggregate_polls(df,method='latest_10',year=2022):
    """Compute daily vote shares using the selected rolling poll average.

    Parameters
    ----------
    df : pd.DataFrame
        Prepared polls for one geography, one row per survey, with data and
        candidate-share columns. Input order breaks ties on the same date.
    method : {'simple', 'latest_10', 'weighted'}
        Simple averages polls aged 0-29 days equally. Latest_10 averages the
        latest ten available polls equally, or all polls if fewer exist.
        Weighted uses polls aged 0-29 days with weights 1 / (age + 1).
    year : int
        Election year determining candidate names and the runoff date.

    Returns
    -------
    pd.DataFrame
        Daily data and candidate shares from September 1 through the runoff.
        Shares remain on the 0-1 scale; dates without eligible polls contain NaN.
    """
    if method not in ['simple','latest_10','weighted']:
        raise ValueError("method must be 'simple', 'latest_10' or 'weighted'")

    candidates, dates = election_settings(year)
    polls      = df[['data']+candidates].copy()
    tracker    = pd.DataFrame(index=dates,columns=candidates,dtype=float)
    latest_age = pd.Series(index=dates,dtype=float)

    polls['data'] = pd.to_datetime(polls['data']).dt.normalize()
    polls = polls.dropna(subset=candidates).sort_values('data',kind='stable')
    for date in dates:
        age = (date-polls['data']).dt.days
        if method == 'latest_10':
            available = polls.loc[age>=0].tail(10)
        else:
            available = polls.loc[age.between(0,29)]
        if available.empty:
            continue
        if method == 'weighted':
            weights = 1/(age.loc[available.index]+1)
            tracker.loc[date] = available[candidates].mul(weights,axis=0).sum()/weights.sum()
        else:
            tracker.loc[date] = available[candidates].mean()
        latest_age.loc[date] = (date-available['data'].iloc[-1]).days

    tracker = tracker.rename_axis('data').reset_index()
    tracker.attrs['method'] = method
    tracker.attrs['latest_poll_age'] = latest_age.dropna().to_dict()
    return tracker


def import_election_results(year,source=None):
    """Read presidential runoff counts and valid vote shares from TSE.

    Parameters
    ----------
    year : int
        Completed presidential runoff year listed in ELECTIONS.
    source : str, path-like or file-like, optional
        Local TSE municipality/zone ZIP. Otherwise reuse a temporary-directory
        archive or download it once from TSE (several hundred MB).

    Returns
    -------
    pd.DataFrame
        sigla_uf, candidate shares, votes_<candidate> and valid_votes.
        Candidate names and ballot numbers follow ELECTIONS for the year.
        Includes the 26 states, DF and overseas votes (ZZ).
    """
    election_settings(year)
    if source is None:
        source = Path(gettempdir())/f'polls_votacao_{year}.zip'
        if not source.exists():
            url     = f'https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_{year}.zip'
            headers = {'User-Agent':'ElectionResearch/1.0 (state-level election analysis)'}
            partial = source.with_suffix('.part')
            with requests.get(url,headers=headers,stream=True,timeout=120) as response, partial.open('wb') as file:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=1024*1024):
                    file.write(chunk)
            partial.replace(source)

    candidates = ELECTIONS[year]['candidates']
    columns    = ['NR_TURNO','CD_CARGO','SG_UF','NR_CANDIDATO','QT_VOTOS_NOMINAIS']
    states     = GEOGRAPHIES
    with ZipFile(source) as archive:
        with archive.open(f'votacao_candidato_munzona_{year}_BR.csv') as file:
            votes = pd.read_csv(file,sep=';',encoding='latin1',usecols=columns)

    votes = votes.loc[(votes['NR_TURNO']==2) & (votes['CD_CARGO']==1)
                      & votes['SG_UF'].isin(states) & votes['NR_CANDIDATO'].isin(candidates)]
    totals = votes.groupby(['SG_UF','NR_CANDIDATO'])['QT_VOTOS_NOMINAIS'].sum().unstack()
    totals = totals.reindex(index=states,columns=list(candidates)).rename(columns=candidates)

    if totals.isna().any().any() or (totals.sum(axis=1)<=0).any():
        raise ValueError('The election data must contain runoff votes for every requested geography.')

    counts = totals.sum(axis=1)
    result = totals.div(counts,axis=0).join(totals.add_prefix('votes_'))

    result['valid_votes'] = counts
    result = result.rename_axis(index='sigla_uf',columns=None).reset_index()
    result.attrs['year'] = year
    return result


def fill_state_trackers(estadual,filler,fill_type='national',year=2022,weights=None,diagnostics=None,show=True):
    """Complete daily state trackers using national polls or historical results.

    Parameters
    ----------
    estadual : dict of pd.DataFrame
        State trackers returned by aggregate_polls, keyed by state abbreviation.
    filler : pd.DataFrame
        National aggregate_polls output or historical election shares.
        National values match by date; historical shares stay constant, mapped
        PT-to-PT and opponent-to-opponent.
    fill_type : {'national', 'previous'}
        Source used to replace missing estimates.
    year : int
        Election being tracked.
    weights : pd.Series, optional
        Prior-election valid votes for coverage. Loaded if omitted.
    diagnostics : dict, optional
        Receives daily coverage/freshness data and the corresponding figure.
    show : bool
        Display the coverage and freshness figure.

    Returns
    -------
    dict of pd.DataFrame
        Independent trackers for all 27 states and ZZ, September 1 through the
        selected runoff date. Existing estimates are preserved. Missing national
        filler values remain NaN; no future observations are carried backward.
    """
    if fill_type not in ['national','previous']:
        raise ValueError("fill_type must be 'national' or 'previous'")

    candidates, dates = election_settings(year)
    completed  = {}

    if fill_type == 'national':
        fallback = filler.set_index(pd.to_datetime(filler['data']))[candidates].reindex(dates)
    else:
        previous, _   = election_settings(year-4)
        historical    = filler.set_index('sigla_uf').rename(columns=dict(zip(previous,candidates)))
        historical = historical.reindex(GEOGRAPHIES)[candidates]
        if historical.isna().any().any():
            raise ValueError('The historical filler must contain shares for all 27 states and ZZ.')

    for state in GEOGRAPHIES:
        tracker = pd.DataFrame(index=dates,columns=candidates,dtype=float)
        if state in estadual:
            polls   = estadual[state]
            tracker = polls.set_index(pd.to_datetime(polls['data']))[candidates].reindex(dates)

        if fill_type == 'national':
            tracker = tracker.fillna(fallback)
        else:
            tracker = tracker.fillna(historical.loc[state])
        completed[state] = tracker.rename_axis('data').reset_index()

    if show or diagnostics is not None:
        if weights is None:
            weights = import_election_results(year-4).set_index('sigla_uf')['valid_votes']
        daily, fig = state_poll_coverage(estadual,weights,year=year)
        if diagnostics is not None:
            diagnostics.update(coverage=daily,coverage_figure=fig)
        if show:
            plt.show()
    return completed


def pollster_composition(nacional,estadual,year=2022):
    """Return survey counts and within-level pollster shares for the tracking period.

    Parameters
    ----------
    nacional : pd.DataFrame
        Prepared national polls.
    estadual : dict
        Prepared state polls, including overseas when available.
    year : int
        Election calendar.

    Returns
    -------
    pd.DataFrame
        National/state survey counts and percentages by institute.
    """
    _, dates = election_settings(year)
    counts   = {}
    for level,frames in [('national',[nacional]),('state',list(estadual.values()))]:
        frame = pd.concat(frames,ignore_index=True) if frames else nacional.iloc[:0]
        frame = frame.loc[frame['data'].between(dates[0],dates[-1])]
        counts[level] = frame.drop_duplicates(['sigla_uf','id_pesquisa']).groupby('instituto').size()
    table = pd.DataFrame(counts).fillna(0).astype(int)

    for level in ['national','state']:
        total = table[level].sum()
        table[level+'_pct'] = 100*table[level]/total if total else float('nan')
    return table


def pollster_accuracy(nacional,estadual,results,candidate=None,year=None):
    """Compare each institute's surveys with final national and state vote shares.

    Parameters
    ----------
    nacional : pd.DataFrame
        Prepared national polls.
    estadual : dict
        Prepared state polls.
    results : pd.DataFrame
        Actual election results, including overseas votes.
    candidate : str, optional
        Defaults to the PT candidate; runoff shares are normalized to valid votes.
    year : int, optional
        Inferred from results. Only the September-to-runoff period is evaluated.

    Returns
    -------
    pd.DataFrame
        Survey counts and average absolute errors in percentage points by institute
        and level. Eligible scenarios are averaged within each survey before taking
        absolute errors. Every survey has equal weight; state polls are compared
        with their own state's result. Polling dates and state mixes can differ.
    """
    year = year or results.attrs.get('year')
    candidates, dates = election_settings(year)
    candidate = candidate or candidates[0]
    actual    = results.set_index('sigla_uf')[candidate].copy()
    actual.loc['BR'] = results['votes_'+candidate].sum()/results['valid_votes'].sum()
    frames = []

    for level,polls in [('National',[nacional]),('State',list(estadual.values()))]:
        frame = pd.concat(polls,ignore_index=True) if polls else nacional.iloc[:0]
        frame = frame.loc[frame['data'].between(dates[0],dates[-1])]
        frame = frame.groupby(['instituto','sigla_uf','id_pesquisa'],as_index=False)[candidate].mean()

        frame['Absolute error (pp)'] = 100*(frame[candidate]-frame['sigla_uf'].map(actual)).abs()
        summary = frame.groupby('instituto')['Absolute error (pp)'].agg(['count','mean']).reset_index()

        summary['Level'] = level
        frames.append(summary.rename(columns={'instituto':'Institute','count':'Surveys','mean':'Average absolute error (pp)'}))
    return pd.concat(frames,ignore_index=True)[['Institute','Level','Surveys','Average absolute error (pp)']]


def state_poll_coverage(estadual,weights,year=2022):
    """Measure coverage and latest-poll age before filling state estimates.

    Parameters
    ----------
    estadual : dict
        Unfilled aggregate_polls outputs, including latest_poll_age metadata.
    weights : pd.Series
        Prior-election valid votes, including ZZ.
    year : int
        Election calendar.

    Returns
    -------
    daily : pd.DataFrame
        Covered vote percentage and weighted latest-poll age among covered states.
        Age is missing when no voting weight is covered.
    fig : matplotlib.figure.Figure
        Coverage and freshness panels.
    """
    candidates, dates = election_settings(year)
    weights = weights.reindex(GEOGRAPHIES)
    if weights.isna().any() or (weights<=0).any() or not (weights<float('inf')).all():
        raise ValueError('Coverage requires positive finite weights for every geography.')
    weights = weights/weights.sum()
    covered = pd.DataFrame(False,index=dates,columns=GEOGRAPHIES)
    ages    = pd.DataFrame(float('nan'),index=dates,columns=GEOGRAPHIES)

    for state,frame in estadual.items():
        covered[state] = frame.set_index('data')[candidates].reindex(dates).notna().all(axis=1)
        ages[state]    = pd.Series(frame.attrs.get('latest_poll_age',{}),dtype=float).reindex(dates)
    share = covered.mul(weights,axis=1).sum(axis=1)
    daily = pd.DataFrame({'coverage_pct':100*share},index=dates)

    daily['latest_poll_age_days'] = ages.where(covered).mul(weights,axis=1).sum(axis=1,min_count=1)/share.where(share>0)
    daily.loc[(covered & ages.isna()).any(axis=1),'latest_poll_age_days'] = float('nan')
    fig,axes = plt.subplots(nrows=1,ncols=2,figsize=(13,5),sharex=True)
    for ax,column,title,label in zip(axes,
                                    ['coverage_pct','latest_poll_age_days'],
                                    ['State polling coverage','Polling freshness among covered states'],
                                    ['Prior-election valid votes (%)','Weighted age of latest poll (days)']):
        ax.plot(dates,daily[column],color=COLORS[0],linewidth=2)
        ax.set_title(title)
        ax.set_ylabel(label)
        ax.set_xlabel('Date')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
        ax.tick_params(axis='x',rotation=30)
    axes[0].set_ylim(0,100)
    axes[1].set_ylim(bottom=0)
    mark_election_dates(fig,year)
    fig.tight_layout()
    return daily.rename_axis('data').reset_index(), fig


def plot_poll_trackers(nacional,national,estadual,from_states,state_polls,candidate=None,year=2022,show=True):
    """Plot national survey observations and the state-aggregated tracker.

    Parameters
    ----------
    nacional : pd.DataFrame
        Prepared national survey scenarios on the two-candidate share scale.
        Multiple eligible scenarios within a survey are averaged for its dot;
        the tracker uses its selected aggregation method.
    national : pd.DataFrame
        National tracker.
    estadual : dict
        Unfilled state trackers; missing polling remains a gap.
    from_states : pd.DataFrame
        Filled and weighted national aggregate.
    state_polls : dict
        Prepared state polls for unique daily survey counts in the lower panel.
        An annotation reports surveys used in the first day's selected average.
    candidate : str, optional
        Defaults to the PT candidate.
    year : int
        Election calendar.
    show : bool
        Display figures.

    Returns
    -------
    dict
        National-poll and state-aggregate figures.
    """
    candidates, dates = election_settings(year)
    candidate = candidate or candidates[0]
    selected  = nacional.loc[nacional['data'].between(dates[0],dates[-1])]
    selected  = selected.groupby(['data','instituto','id_pesquisa'],as_index=False)[candidate].mean()
    fig,ax    = plt.subplots(figsize=(10,5))
    ax.scatter(selected['data'],100*selected[candidate],facecolors='none',edgecolors=COLORS[3],label='Poll observations')
    ax.plot(national['data'],100*national[candidate],color=COLORS[0],linewidth=2.5,label='National tracker')
    figures = {'national_polls':fig}

    fig,axes = plt.subplots(nrows=2,ncols=1,figsize=(11,8),sharex=True,gridspec_kw={'height_ratios':[2,1]})
    ax       = axes[0]
    bottom   = pd.Series(0,index=dates)
    counts   = pd.DataFrame(0,index=dates,columns=MAIN_STATES)
    initial  = pd.Series(0,index=MAIN_STATES)

    for state in MAIN_STATES:
        frame = estadual.get(state,pd.DataFrame({'data':dates,candidate:float('nan')}))
        label = state if frame[candidate].notna().any() else state+' (no polls)'
        ax.plot(frame['data'],100*frame[candidate],color=STATE_COLORS[state],linewidth=1.6,alpha=0.9,label=label)
        if state in state_polls:
            counts[state] = state_polls[state].groupby('data')['id_pesquisa'].nunique().reindex(dates,fill_value=0)
            polls = state_polls[state]
            if national.attrs.get('method','latest_10') == 'latest_10':
                initial[state] = min(10,len(polls.loc[polls['data']<=dates[0]]))
            else:
                initial[state] = len(polls.loc[polls['data'].between(dates[0]-pd.Timedelta(days=29),dates[0])])
        axes[1].bar(dates,counts[state],bottom=bottom,width=0.85,color=STATE_COLORS[state],label=state)
        bottom += counts[state]
    ax.plot(from_states['data'],100*from_states[candidate],color=COLORS[0],linewidth=3,label='State aggregate')
    ax.set_title('State trackers')
    axes[1].set_title('New state surveys')
    axes[1].set_ylabel('Number of surveys')
    axes[1].set_xlabel('Date')
    axes[1].yaxis.set_major_locator(MaxNLocator(integer=True))
    axes[1].set_ylim(bottom=0)
    initial_label = ' | '.join(f'{state}: {initial[state]}' for state in MAIN_STATES)
    window_label = 'up to 10' if national.attrs.get('method','latest_10') == 'latest_10' else '30-day window'
    axes[1].text(0.02,0.95,f'Surveys in initial average on {dates[0]:%d %b} ({window_label}):\n{initial_label}',
                 transform=axes[1].transAxes,va='top',color=COLORS[0])
    figures['state_aggregate'] = fig

    for fig in figures.values():
        ax = fig.axes[0]
        ax.set_ylabel(f'{candidate} vote share (%)')
        ax.legend(loc=0)
        for axis in fig.axes:
            axis.set_xlim(dates[0]-pd.Timedelta(days=0.5),dates[-1]+pd.Timedelta(days=0.5))
            axis.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
        fig.axes[-1].set_xlabel('Date')
        mark_election_dates(fig,year)
        fig.tight_layout()
    if show:
        plt.show()
    return figures


def decompose_state_errors(completed,results,weights,candidate=None,year=None,show=True):
    """Decompose national error into state estimation and voting-weight effects.

    Parameters
    ----------
    completed : dict
        Filled state trackers used in the national aggregate.
    results : pd.DataFrame
        Current-election results including ZZ.
    weights : pd.Series
        Prior-election valid votes used in aggregation.
    candidate : str, optional
        Defaults to the PT candidate.
    year : int, optional
        Inferred from results metadata.
    show : bool
        Display the signed stacked-area chart.

    Returns
    -------
    contributions : pd.DataFrame
        Daily SP, MG, RJ, BA, PR, Other and weight-change contributions in pp,
        and their sum, equal to the aggregate error against actual national votes.
    fig : matplotlib.figure.Figure
        Positive/negative stacked contributions and total national error.
    """
    year = year or results.attrs.get('year')
    candidates, dates = election_settings(year)
    candidate = candidate or candidates[0]
    national  = aggregate_states(completed,weights,year=year)
    actual    = results.set_index('sigla_uf').reindex(GEOGRAPHIES)
    weights   = weights.reindex(GEOGRAPHIES)/weights.reindex(GEOGRAPHIES).sum()
    current   = actual['valid_votes']/actual['valid_votes'].sum()
    shares    = pd.DataFrame({uf:frame.set_index('data')[candidate] for uf,frame in completed.items()}).reindex(dates)
    errors    = 100*shares.sub(actual[candidate],axis=1).mul(weights,axis=1)
    other     = [uf for uf in GEOGRAPHIES if uf not in MAIN_STATES]
    contributions = errors[MAIN_STATES].copy()

    contributions['Other'] = errors[other].sum(axis=1,min_count=len(other))
    # Prior-election weights differ from the weights in the actual national result.
    contributions['Voting-weight change'] = 100*((weights-current)*actual[candidate]).sum()
    contributions.loc[shares.isna().any(axis=1)] = float('nan')
    columns = contributions.columns.tolist()
    contributions['National error'] = 100*(national.set_index('data')[candidate]-(actual[candidate]*current).sum())
    fig,ax = plt.subplots(figsize=(12,6))
    colors   = [STATE_COLORS[state] for state in MAIN_STATES]+['#C5CBD0','#795548']
    patterns = ['', '', '', '/', '\\', '..', 'xx']
    positive = ax.stackplot(dates,contributions[columns].clip(lower=0).to_numpy().T,labels=columns,colors=colors,alpha=0.9)
    negative = ax.stackplot(dates,contributions[columns].clip(upper=0).to_numpy().T,colors=colors,alpha=0.9)
    for upper,lower,pattern in zip(positive,negative,patterns):
        for area in [upper,lower]:
            area.set_hatch(pattern)
            area.set_edgecolor('white')
            area.set_linewidth(0.4)
    ax.plot(dates,contributions['National error'],color=COLORS[0],linewidth=2,label='National error')
    ax.axhline(0,color=COLORS[0],linewidth=0.8)
    ax.set_ylabel(f'{candidate} error contribution (pp)')
    ax.set_xlabel('Date')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    ax.legend(loc=0,ncol=2)
    mark_election_dates(fig,year)
    fig.tight_layout()
    if show:
        plt.show()
    return contributions.rename_axis('data').reset_index(), fig


def aggregate_states(estadual_full,weights,year=2022):
    """Aggregate state trackers using fixed state voting weights.

    Parameters
    ----------
    estadual_full : dict of pd.DataFrame
        Daily trackers for all 27 states and ZZ, as returned by fill_state_trackers.
    weights : pd.Series
        Positive vote counts or weights indexed by state abbreviation.
        Values are normalized internally; use prior-election valid_votes.
    year : int
        Election being tracked.

    Returns
    -------
    pd.DataFrame
        Daily data and candidate shares. A missing state/date estimate
        makes the entire national estimate missing on that date.
    """
    if set(estadual_full) != set(GEOGRAPHIES):
        raise ValueError('estadual_full must contain the 27 states and overseas (ZZ).')
    weights = weights.reindex(GEOGRAPHIES)
    if weights.isna().any() or (weights<=0).any() or not (weights<float('inf')).all():
        raise ValueError('weights must contain finite positive values for all 27 states and ZZ.')
    weights = weights/weights.sum()
    candidates, dates = election_settings(year)
    tracker = pd.DataFrame(index=dates)
    missing = pd.Series(False,index=dates)

    for candidate in candidates:
        shares = pd.concat({uf:df.set_index(pd.to_datetime(df['data']))[candidate]
                            for uf,df in estadual_full.items()},axis=1).reindex(dates)
        missing = missing | shares.isna().any(axis=1)
        tracker[candidate] = shares.mul(weights,axis=1).sum(axis=1,min_count=len(GEOGRAPHIES))

    tracker.loc[missing] = float('nan')
    return tracker.rename_axis('data').reset_index()


def evaluate_tracker(tracker,results,level='national',year=None):
    """Compare daily estimates with final runoff shares for one election.

    Parameters
    ----------
    tracker : pd.DataFrame or dict of pd.DataFrame
        National tracker, or state trackers keyed by abbreviation.
    results : pd.DataFrame
        import_election_results output, including overseas vote counts.
    level : {'national', 'state'}
        Geography of the estimates.
    year : int, optional
        Inferred from results.attrs when omitted.

    Returns
    -------
    daily : pd.DataFrame
        Date, geography, candidate, estimate, actual, error_pp and abs_error_pp.
        Signed error is estimate minus actual. Missing estimates stay missing.
    summary : pd.DataFrame
        Runoff-day signed and absolute errors in percentage points.
    """
    if level not in ['national','state']:
        raise ValueError("level must be 'national' or 'state'")
    year = year or results.attrs.get('year')
    if year is None:
        raise ValueError('Pass year when results have no election-year metadata.')
    if results.attrs.get('year',year) != year:
        raise ValueError('The requested year differs from the election results.')
    candidates, dates = election_settings(year)
    actual = results.set_index('sigla_uf')

    if level == 'national':
        states = GEOGRAPHIES
        counts = actual.reindex(states)[['votes_'+name for name in candidates]]
        if counts.isna().any().any():
            raise ValueError('Results lack vote counts for the requested national coverage.')
        totals   = counts.sum()
        actual   = pd.DataFrame([totals.to_numpy()/totals.sum()],index=['BR'],columns=candidates)
        trackers = {'BR':tracker}
    else:
        trackers = tracker

    frames = []
    for state,frame in trackers.items():
        if frame.attrs.get('year',year) != year:
            raise ValueError('Tracker and results refer to different elections.')
        frame = frame.set_index(pd.to_datetime(frame['data']))[candidates].reindex(dates).rename_axis('data').reset_index()
        daily = frame[['data']+candidates].melt(id_vars='data',var_name='candidate',value_name='estimate')

        daily['data']         = pd.to_datetime(daily['data'])
        daily['sigla_uf']     = state
        daily['actual']       = daily['candidate'].map(actual.loc[state,candidates])
        daily['error_pp']     = 100*(daily['estimate']-daily['actual'])
        daily['abs_error_pp'] = daily['error_pp'].abs()
        frames.append(daily)

    daily   = pd.concat(frames,ignore_index=True)
    keys    = ['sigla_uf','candidate']
    final = daily.loc[daily['data']==dates[-1],keys+['error_pp','abs_error_pp']]
    final = final.rename(columns={'error_pp':'final_error_pp','abs_error_pp':'final_abs_error_pp'})
    return daily, final.reset_index(drop=True)


def build_trackers(year=2022,method='latest_10',filler='previous',poll_source='data/data.csv',institutes=SELECTED_INSTITUTES):
    """Build national-poll and state-aggregated national FINAL trackers.

    Parameters
    ----------
    year : {2006, 2010, 2014, 2018, 2022}
        Completed runoff year. The preceding election must also have a runoff.
    method : {'simple', 'latest_10', 'weighted'}
        Equal-weight 30-day mean, equal-weight latest-ten mean, or 30-day
        mean weighted by 1 / (days since release + 1).
    filler : {'previous', 'national', 'previous_only'}
        Previous election (year-4) runoff shares or same-day national polls. Historical
        mapping is PT-to-PT and opponent-to-opponent, not personal continuity.
        'previous_only' uses historical shares for every state and date,
        ignoring current state polls in the state-aggregated tracker.
    poll_source : str or path-like
        Poll CSV path.
    institutes : list of str or None
        Defaults to the original institute selection; None retains all.

    Returns
    -------
    national, from_states : pd.DataFrame
        FINAL tables: data and two candidate-share columns on the 0-1 scale,
        September 1 through the runoff date. Election and method metadata are
        stored in attrs. State aggregation always uses year-4 valid-vote counts,
        including overseas votes. The wrapper does not evaluate or plot.
    """
    candidates, dates = election_settings(year)
    if year-4 not in ELECTIONS:
        raise ValueError('The wrapper requires a preceding presidential runoff; supported years start at 2006.')
    if filler not in ['previous','national','previous_only']:
        raise ValueError("filler must be 'previous', 'national' or 'previous_only'")

    nacional, estadual = import_prepared_data(year=year,source=poll_source,institutes=institutes,show=False)
    national = aggregate_polls(nacional,method=method,year=year)
    trackers = {} if filler == 'previous_only' else {uf:aggregate_polls(df,method=method,year=year) for uf,df in estadual.items()}
    previous = import_election_results(year=year-4)
    weights  = previous.set_index('sigla_uf')['valid_votes']
    if filler == 'national':
        completed = fill_state_trackers(trackers,national,year=year,show=False)
    else:
        completed = fill_state_trackers(trackers,previous,fill_type='previous',year=year,show=False)
    from_states = aggregate_states(completed,weights,year=year)

    national.attrs.update(year=year,method=method,kind='national_polls')
    from_states.attrs.update(year=year,method=method,kind='state_aggregate',filler=filler,weights_year=year-4)
    return national, from_states


def compare_trackers(results,candidate=None,show=True,year=None,**trackers):
    """Compare any number of named FINAL trackers with election results.

    Parameters
    ----------
    results : pd.DataFrame
        import_election_results output for the evaluated election.
    candidate : str, optional
        Candidate to report and plot; defaults to the PT candidate.
    show : bool
        Show the charts and print the summary. False returns them silently.
    year : int, optional
        Election year, inferred from results.attrs when omitted.
    **trackers : pd.DataFrame
        Named FINAL tables, e.g. national_polls=national, states_previous=states.

    Returns
    -------
    daily_errors : pd.DataFrame
        Estimates, actual shares and signed/absolute percentage-point errors,
        with method labels.
    summary : pd.DataFrame
        Runoff-day signed and absolute errors by method and candidate.
        Missing runoff-day estimates remain missing.
    figures : dict of matplotlib.figure.Figure
        Vote-share and daily absolute-error comparisons. No files are exported.
    """
    if not trackers:
        raise ValueError('Pass at least one named FINAL tracker.')
    year = year or results.attrs.get('year')
    candidates, dates = election_settings(year)
    candidate = candidate or candidates[0]
    if candidate not in candidates:
        raise ValueError('Select a candidate in this election.')

    evaluations = {name:evaluate_tracker(df,results,year=year) for name,df in trackers.items()}
    daily = pd.concat({name:value[0] for name,value in evaluations.items()},names=['method']).reset_index(level=0).reset_index(drop=True)
    summary = pd.concat({name:value[1] for name,value in evaluations.items()},names=['method']).reset_index(level=0).reset_index(drop=True)
    summary = summary.loc[summary['candidate']==candidate].reset_index(drop=True)
    selected = daily.loc[daily['candidate']==candidate]
    fig,ax   = plt.subplots(figsize=(10,5))
    for name,frame in selected.groupby('method',sort=False):
        color = COLORS[0] if name.startswith('National polls') else COLORS[1] if name.startswith('State aggregate') else None
        style = '--' if '(shared institutes)' in name else '-'
        ax.plot(frame['data'],100*frame['estimate'],color=color,linestyle=style,label=name.replace('_',' ').capitalize())
    ax.axhline(100*selected['actual'].iloc[0],color=COLORS[2],linestyle='--',label='Actual result')
    ax.set_ylabel(f'{candidate} vote share (%)')
    ax.set_xlabel('Date')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    ax.legend(loc=0)
    mark_election_dates(fig,year)
    fig.tight_layout()
    figures = {'shares':fig}

    fig,ax = plt.subplots(figsize=(10,5))
    for name,frame in selected.groupby('method',sort=False):
        color = COLORS[0] if name.startswith('National polls') else COLORS[1] if name.startswith('State aggregate') else None
        style = '--' if '(shared institutes)' in name else '-'
        ax.plot(frame['data'],frame['abs_error_pp'],color=color,linestyle=style,label=name.replace('_',' ').capitalize())
    ax.set_ylabel(f'{candidate} absolute error (pp)')
    ax.set_xlabel('Date')
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    ax.legend(loc=0)
    mark_election_dates(fig,year)
    fig.tight_layout()
    figures['abs_error_pp'] = fig

    if show:
        print(summary.to_string(index=False))
        plt.show()
    return daily, summary, figures


if __name__ == '__main__':
    method            = 'weighted'  # 'simple', 'latest_10' or 'weighted'
    year              = 2022
    nacional, estadual = import_prepared_data(year=year)
    previous          = import_election_results(year=year-4)
    results           = import_election_results(year=year)
    weights           = previous.set_index('sigla_uf')['valid_votes']
    national          = aggregate_polls(nacional,method=method,year=year)
    state_trackers    = {uf:aggregate_polls(df,method=method,year=year) for uf,df in estadual.items()}
    diagnostics       = {}
    completed_previous = fill_state_trackers(
        estadual    = state_trackers,
        filler      = previous,
        fill_type   = 'previous',
        year        = year,
        weights     = weights,
        diagnostics = diagnostics,
        show        = False
    )
    states_previous = aggregate_states(completed_previous,weights,year=year)
    tracker_figures = plot_poll_trackers(nacional,national,state_trackers,states_previous,estadual,year=year,show=False)
    state_errors, state_error_figure = decompose_state_errors(completed_previous,results,weights,year=year,show=False)
    institute_accuracy = pollster_accuracy(nacional,estadual,results,year=year)
    composition        = pollster_composition(nacional,estadual,year=year)
    accuracy           = institute_accuracy.pivot(index='Institute',columns='Level',values='Average absolute error (pp)')
    institute_summary  = composition.rename(columns={'national':'National surveys','state':'State surveys',
                                                     'national_pct':'National share (%)','state_pct':'State share (%)'})

    institute_summary['National error (pp)'] = accuracy.reindex(columns=['National'])['National']
    institute_summary['State error (pp)']    = accuracy.reindex(columns=['State'])['State']
    institute_summary = institute_summary[['National surveys','National share (%)','National error (pp)',
                                           'State surveys','State share (%)','State error (pp)']].rename_axis('Institute')
    print('\nInstitute composition and accuracy (tracking period; errors are average absolute errors with equal survey weights):')
    print(institute_summary.to_string(float_format=lambda x:f'{x:.2f}',na_rep='—'))

    # Hold the available institute set constant across national and state polling.
    common      = composition.index[(composition['national']>0) & (composition['state']>0)].tolist()
    print('\nInstitutes present at both levels during the tracking period:',', '.join(common) or 'None')
    if common:
        matched_national = nacional.loc[nacional['instituto'].isin(common)]
        national_common  = aggregate_polls(matched_national,method=method,year=year)
        common_errors, common_summary, common_figures = compare_trackers(
            results = results,
            show    = False,
            **{'National polls (all selected institutes)':national,
               'State aggregate (all selected institutes)':states_previous,
               'National polls (shared institutes)':national_common}
        )
        print('\nAll selected vs shared institutes (institute frequencies and geographic coverage can still differ):')
        print(common_summary.to_string(index=False))
    plt.show()
