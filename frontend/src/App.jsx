import { startTransition, useEffect, useMemo, useState } from 'react';
import Plot from 'react-plotly.js';
import { postJson, uploadFiles } from './api';
import bremboLogo from './assets/Brembo-Logo.jpg';
import bremboLogoTransparent from './assets/Brembo-Logo-transparent.png';
import launchVideo from './assets/Launch-Page.mp4';

const SALES_COLORS = ['#ef3340', '#008000', '#5c6bf2', '#f4a261'];
const OPAQUE_HOVER_LABEL = {
  bgcolor: 'rgba(255,255,255,1)',
  bordercolor: '#111111',
  font: { color: '#111111', family: 'Bahnschrift, Segoe UI, sans-serif', size: 12 },
  align: 'left',
};
const DIO_HOVER_LABEL = {
  bgcolor: 'rgba(95,95,95,1)',
  bordercolor: 'rgba(95,95,95,1)',
  font: { color: '#ffffff', family: 'Bahnschrift, Segoe UI, sans-serif', size: 12 },
  align: 'left',
};
const COST_BREAKDOWN_ORDER = [
  'Rebate',
  'Freight Out',
  'Purchasing Material',
  'Warehouse Operation',
  'Commission',
  'Other SG&A',
  'EBIT',
];
const COST_COLOR_BY_CATEGORY = {
  Rebate: '#a9b7ff',
  'Freight Out': '#b7e4ff',
  'Purchasing Material': '#7dded0',
  'Warehouse Operation': '#ffd6a5',
  Commission: '#ff9faf',
  'Other SG&A': '#c9b6ff',
  EBIT: '#9ee6c8',
};
const INVENTORY_CATEGORIES = [
  { label: 'Total Inventory', value: 'Total Inventory' },
  { label: 'AM Traditional', value: 'AM Traditional' },
  { label: 'AM Traditional - Pads', value: 'Pads' },
  { label: 'AM Traditional - Disc', value: 'Disc' },
  { label: 'Moto', value: 'Moto' },
  { label: 'Fluid', value: 'Fluid' },
];
const PIE_SOURCES = ['Overall', 'Pads', 'Disc'];
const COVERAGE_SOURCES = ['Overall', 'Pads', 'Disc'];

function buildDefaultFilter(metadata, label = 'Filter 1') {
  const salesFilters = metadata?.salesFilters;
  const dates = salesFilters?.dateOptions || [];
  return {
    label,
    startDate: dates[0] || '',
    endDate: dates[dates.length - 1] || '',
    regions: ['ALL Region'],
    countries: ['ALL Country'],
    productTypes: ['ALL Product Type'],
    itemGroups: ['ALL Item Group'],
    customers: ['ALL Customer'],
    itemCodes: ['ALL Item Code'],
  };
}

function formatMoney(value) {
  if (value == null) {
    return '-';
  }
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value) {
  if (value == null) {
    return '-';
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatShortNumber(value) {
  if (value == null || Number.isNaN(value)) {
    return '';
  }

  const absolute = Math.abs(value);
  if (absolute >= 1000000) {
    return `${(value / 1000000).toFixed(absolute >= 10000000 ? 0 : 1)}M`;
  }
  if (absolute >= 1000) {
    return `${(value / 1000).toFixed(0)}k`;
  }
  return `${value.toFixed(0)}`;
}

function pieTextPosition(items) {
  const total = items.reduce((sum, item) => sum + Math.abs(item.value || 0), 0);
  return items.map((item) => (total > 0 && Math.abs(item.value || 0) / total >= 0.08 ? 'inside' : 'outside'));
}

function pieTextTemplate(items) {
  const total = items.reduce((sum, item) => sum + Math.abs(item.value || 0), 0);
  return items.map((item) => (total > 0 && Math.abs(item.value || 0) / total >= 0.08 ? '%{label}<br>%{percent}' : '%{percent}'));
}

function buildSeriesFigure(series, title, yAxisTitle, aggregation, valueFormatter = '%{y:,.2f}', percent = false, textFormatter = formatShortNumber) {
  return {
    data: series.map((entry, index) => ({
      type: aggregation === 'yearly' ? 'bar' : 'scatter',
      mode: aggregation === 'yearly' ? undefined : 'lines+markers+text',
      name: entry.name,
      x: entry.data.map((point) => point.x),
      y: entry.data.map((point) => point.value),
      text: entry.data.map((point) => textFormatter(point.value)),
      textposition: 'top center',
      textfont: { color: '#0f1115', size: 11, family: 'Bahnschrift, Segoe UI, sans-serif' },
      marker: { color: SALES_COLORS[index % SALES_COLORS.length], size: 8 },
      line: { color: SALES_COLORS[index % SALES_COLORS.length], width: 3, shape: 'spline' },
      customdata: entry.data.map((point) => point.mom),
      hovertemplate: `%{x}<br>${title}: ${valueFormatter}<br>MoM: %{customdata:.2%}<extra></extra>`,
    })),
    layout: {
      title: { text: `<b>${title}</b>`, x: 0.5, xanchor: 'center' },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: '#ffffff',
      font: { color: '#20242b', family: 'Inter, sans-serif' },
      legend: { orientation: 'h', x: 0.98, xanchor: 'right', y: 1.08, yanchor: 'top' },
      hoverlabel: OPAQUE_HOVER_LABEL,
      margin: { l: 64, r: 28, t: 62, b: 54 },
      xaxis: {
        title: aggregation === 'yearly' ? 'Year' : 'Date/Year',
        showgrid: false,
        tickformat: aggregation === 'yearly' ? '%Y' : '%y-%m',
        nticks: 5,
      },
      yaxis: {
        title: yAxisTitle,
        tickformat: percent ? '.1%' : undefined,
        tickformatstops: percent
          ? [
              { dtickrange: [null, 0.001], value: '.2%' },
              { dtickrange: [0.001, 0.01], value: '.1%' },
              { dtickrange: [0.01, null], value: '.0%' },
            ]
          : undefined,
        showgrid: false,
        nticks: 4,
        automargin: true,
      },
      hovermode: 'x unified',
    },
    config: { displayModeBar: false, responsive: true },
  };
}

function buildCostBreakdownFigure(breakdowns) {
  const availableCategories = COST_BREAKDOWN_ORDER.filter((category) =>
    breakdowns.some((breakdown) => breakdown.items.some((item) => item.category === category)),
  );
  const columnPositions = breakdowns.length > 1 ? [0.38, 0.74] : [0.64];
  const rowForCategory = (category) => availableCategories.length - availableCategories.indexOf(category);

  return {
    data: breakdowns.map((breakdown, filterIndex) => {
      const ordered = availableCategories
        .map((category) => breakdown.items.find((item) => item.category === category))
        .filter(Boolean);
      const markerSizes = ordered.map((item) => Math.max(8, Math.min(72, Math.sqrt(Math.abs(item.percentage || 0)) * 88)));

      return {
        type: 'scatter',
        mode: 'markers+text',
        name: breakdown.name,
        x: ordered.map(() => columnPositions[filterIndex] || columnPositions[0]),
        y: ordered.map((item) => rowForCategory(item.category)),
        text: ordered.map((item) => formatPercent(item.percentage)),
        customdata: ordered.map((item) => [item.category, item.absoluteValue, item.percentage]),
        hovertemplate: 'Category=%{customdata[0]}<br>Absolute Value=%{customdata[1]:,.0f}<br>Percent=%{customdata[2]:.2%}<extra></extra>',
        marker: {
          size: markerSizes,
          color: ordered.map((item) => COST_COLOR_BY_CATEGORY[item.category] || '#d5dbe7'),
          opacity: 0.85,
          sizemode: 'diameter',
        },
        textposition: 'middle center',
      };
    }),
    layout: {
      title: { text: '<b>Cost Breakdown</b>', x: 0.5, xanchor: 'center' },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: '#ffffff',
      font: { color: '#20242b', family: 'Inter, sans-serif' },
      hoverlabel: OPAQUE_HOVER_LABEL,
      margin: { l: 190, r: 60, t: 72, b: 32 },
      xaxis: { visible: false, range: [0, 1] },
      yaxis: {
        tickvals: availableCategories.map(rowForCategory),
        ticktext: availableCategories,
        title: 'Category',
        range: [0.4, availableCategories.length + 0.9],
        showgrid: false,
        zeroline: false,
      },
      showlegend: false,
      annotations: breakdowns.map((breakdown, index) => ({
        text: `<b>${breakdown.name}</b>`,
        x: columnPositions[index] || columnPositions[0],
        y: availableCategories.length + 0.6,
        xref: 'x',
        yref: 'y',
        showarrow: false,
        font: { size: 14, color: '#0f1115' },
      })),
    },
    config: { displayModeBar: false, responsive: true },
  };
}

function buildInventoryPieFigure(items, title) {
  return {
    data: [
      {
        type: 'pie',
        labels: items.map((item) => item.label),
        values: items.map((item) => item.value),
        hole: 0.58,
        textinfo: 'label+percent',
        textposition: 'outside',
        texttemplate: '%{label}<br>%{percent}',
        insidetextorientation: 'horizontal',
        textfont: { size: 11, color: '#243b5a' },
        hovertemplate: 'Category=%{label}<br>Absolute Value=%{value:,.0f}<br>Percent=%{percent}<extra></extra>',
        sort: false,
        automargin: false,
        domain: { x: [0.12, 0.88], y: [0.06, 0.78] },
        marker: {
          colors: ['#5c6bf2', '#ef5038', '#00c49a', '#a855f7', '#f4a261', '#94a3b8'],
          line: { color: '#ffffff', width: 1 },
        },
      },
    ],
    layout: {
      title: { text: `<b>${title}</b>`, x: 0.5, y: 0.96, xanchor: 'center', yanchor: 'top' },
      paper_bgcolor: 'rgba(0,0,0,0)',
      font: { color: '#20242b', family: 'Inter, sans-serif' },
      hoverlabel: OPAQUE_HOVER_LABEL,
      margin: { l: 70, r: 70, t: 86, b: 42 },
      showlegend: false,
      uniformtext: { minsize: 9, mode: 'show' },
      annotations: [
        {
          text: `${items.length}<br>categories`,
          x: 0.5,
          y: 0.42,
          showarrow: false,
          font: { size: 11, color: '#6e737b' },
        },
      ],
    },
    config: { displayModeBar: false, responsive: true },
  };
}

function buildDioFigure(points) {
  return {
    data: [
      {
        type: 'bar',
        name: 'Net Sales',
        x: points.map((point) => point.yearMonth),
        y: points.map((point) => point.netSales),
        marker: { color: '#9ed8ff' },
        hovertemplate: 'Amount: %{y:,.2f}<br>Date: %{x}<extra>Net Sales</extra>',
      },
      {
        type: 'scatter',
        mode: 'lines+markers',
        name: 'Inventory Value',
        x: points.map((point) => point.yearMonth),
        y: points.map((point) => point.inventoryValue),
        yaxis: 'y2',
        line: { color: '#ef3340', width: 3 },
        hovertemplate: 'Amount: %{y:,.2f}<br>Date: %{x}<extra>Inventory Value</extra>',
      },
      {
        type: 'scatter',
        mode: 'lines+markers+text',
        name: 'DIO',
        x: points.map((point) => point.yearMonth),
        y: points.map((point) => point.dio),
        text: points.map((point) => (point.dio == null ? '' : `${point.dio.toFixed(0)}`)),
        textposition: 'top center',
        yaxis: 'y3',
        line: { color: '#008a2e', width: 2, dash: 'dot' },
        marker: { color: '#008a2e' },
        hovertemplate: 'DIO: %{y:,.2f}<br>Date: %{x}<extra>DIO</extra>',
      },
    ],
    layout: {
      title: { text: '<b>Inventory Value and DIO</b>', x: 0.5, y: 0.98, xanchor: 'center', yanchor: 'top' },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: '#ffffff',
      font: { color: '#20242b', family: 'Inter, sans-serif' },
      margin: { l: 62, r: 82, t: 92, b: 54 },
      hoverlabel: DIO_HOVER_LABEL,
      hovermode: 'closest',
      legend: { orientation: 'h', x: 0.02, y: 1.03, yanchor: 'bottom' },
      xaxis: {
        title: 'Time',
        gridcolor: '#e8eaed',
      },
      yaxis: {
        title: { text: 'Net Sales', font: { color: '#338dcc' } },
        tickfont: { color: '#338dcc' },
        gridcolor: '#e8eaed',
      },
      yaxis2: {
        title: { text: 'Inventory Value', font: { color: '#ef3340' } },
        tickfont: { color: '#ef3340' },
        overlaying: 'y',
        side: 'right',
        showgrid: false,
      },
      yaxis3: {
        visible: false,
        overlaying: 'y',
        side: 'right',
        anchor: 'free',
        position: 0.96,
        showgrid: false,
      },
    },
    config: { displayModeBar: false, responsive: true },
  };
}

function SearchableSelectField({ label, options, value, onChange }) {
  const [query, setQuery] = useState('');
  const normalizedOptions = options.map((option) => (typeof option === 'string' ? { label: option, value: option } : option));
  const selectedOption = normalizedOptions.find((option) => option.value === value);
  const visibleOptions = normalizedOptions.filter((option) => option.label.toLowerCase().includes(query.trim().toLowerCase()));

  function handleSelect(nextValue, event) {
    onChange(nextValue);
    setQuery('');
    const details = event.currentTarget.closest('details');
    if (details) {
      details.open = false;
    }
  }

  return (
    <label className="field searchable-field">
      <span>{label}</span>
      <details className="searchable-select">
        <summary>{selectedOption?.label || 'Select...'}</summary>
        <div className="searchable-select-menu">
          <input
            type="search"
            value={query}
            placeholder="Search..."
            onChange={(event) => setQuery(event.target.value)}
            onClick={(event) => event.stopPropagation()}
          />
          <div className="searchable-options">
            {visibleOptions.length ? (
              visibleOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={option.value === value ? 'searchable-option selected' : 'searchable-option'}
                  onClick={(event) => handleSelect(option.value, event)}
                >
                  {option.label}
                </button>
              ))
            ) : (
              <div className="searchable-empty">No results</div>
            )}
          </div>
        </div>
      </details>
    </label>
  );
}

function MultiSelectField({ label, options, value, onChange }) {
  const [query, setQuery] = useState('');
  const selected = value || [];
  const displayValue = selected.length === 1 ? selected[0] : `${selected.length} selected`;
  const visibleOptions = options.filter((option) => option.toLowerCase().includes(query.trim().toLowerCase()));

  function toggleOption(option) {
    const allOption = options[0];
    if (option === allOption) {
      onChange([allOption]);
      return;
    }

    const withoutAll = selected.filter((item) => item !== allOption);
    const next = withoutAll.includes(option)
      ? withoutAll.filter((item) => item !== option)
      : [...withoutAll, option];
    onChange(next.length ? next : [allOption]);
  }

  return (
    <div className="field field-multi">
      <span>{label}</span>
      <details className="multi-dropdown">
        <summary>{displayValue || 'Select...'}</summary>
        <div className="multi-dropdown-menu">
          <input
            type="search"
            className="multi-search"
            value={query}
            placeholder="Search..."
            onChange={(event) => setQuery(event.target.value)}
            onClick={(event) => event.stopPropagation()}
          />
          {visibleOptions.length ? (
            visibleOptions.map((option) => (
              <label key={option} className={selected.includes(option) ? 'multi-option selected' : 'multi-option'}>
                <input
                  type="checkbox"
                  checked={selected.includes(option)}
                  onChange={() => toggleOption(option)}
                />
                <span>{option}</span>
              </label>
            ))
          ) : (
            <div className="multi-empty">No results</div>
          )}
        </div>
      </details>
    </div>
  );
}

function FilterCard({ title, filter, metadata, onChange, onRemove, removable }) {
  const salesFilters = metadata?.salesFilters;
  return (
    <div className="filter-card">
      <div className="filter-card-header">
        <div>
          <p className="eyebrow">Comparison</p>
          <h3>{title}</h3>
        </div>
        {removable ? (
          <button type="button" className="ghost-button" onClick={onRemove}>
            Remove
          </button>
        ) : null}
      </div>
      <div className="filter-grid">
        <SearchableSelectField
          label="Start Date"
          options={salesFilters?.dateOptions || []}
          value={filter.startDate}
          onChange={(startDate) => onChange({ ...filter, startDate })}
        />
        <SearchableSelectField
          label="End Date"
          options={salesFilters?.dateOptions || []}
          value={filter.endDate}
          onChange={(endDate) => onChange({ ...filter, endDate })}
        />
        <MultiSelectField
          label="Region"
          options={salesFilters?.regions || []}
          value={filter.regions}
          onChange={(regions) => onChange({ ...filter, regions })}
        />
        <MultiSelectField
          label="Country"
          options={salesFilters?.countries || []}
          value={filter.countries}
          onChange={(countries) => onChange({ ...filter, countries })}
        />
        <MultiSelectField
          label="Product Type"
          options={salesFilters?.productTypes || []}
          value={filter.productTypes}
          onChange={(productTypes) => onChange({ ...filter, productTypes })}
        />
        <MultiSelectField
          label="Item Group"
          options={salesFilters?.itemGroups || []}
          value={filter.itemGroups}
          onChange={(itemGroups) => onChange({ ...filter, itemGroups })}
        />
        <MultiSelectField
          label="Customer"
          options={salesFilters?.customers || []}
          value={filter.customers}
          onChange={(customers) => onChange({ ...filter, customers })}
        />
        <MultiSelectField
          label="Item Code"
          options={salesFilters?.itemCodes || []}
          value={filter.itemCodes}
          onChange={(itemCodes) => onChange({ ...filter, itemCodes })}
        />
      </div>
    </div>
  );
}

function InventoryCard({ title, amount, quantity, details, mom }) {
  const positive = mom != null && mom >= 0;
  const deltaLabel = mom == null ? 'No MoM' : `${positive ? '▲ +' : '▼ '}${formatPercent(mom)} MoM`;
  return (
    <article className={`inventory-card${details?.length ? ' inventory-card-with-details' : ''}`}>
      <h3>{title}</h3>
      <div className="inventory-card-value">¥{formatMoney(amount)}</div>
      {quantity != null ? <div className="inventory-card-meta">Qty {formatMoney(quantity)}</div> : null}
      {details?.length ? (
        <div className="inventory-card-breakdown">
          {details.map((detail) => (
            <div key={detail.label}>{detail.label}: ¥{formatMoney(detail.value)}</div>
          ))}
        </div>
      ) : null}
      <div className={`delta ${mom == null ? 'delta-neutral' : positive ? 'delta-up' : 'delta-down'}`}>
        {deltaLabel}
      </div>
    </article>
  );
}

function InventoryNote() {
  const notes = [
    ['Quality Location', "Refers to the 'NC' and 'QC' Warehouse Location."],
    ['Obsolete', 'Items filtered out by cross-referencing against the Obsolete table.'],
    ['New Entry', 'Any record whose created date is on or after January 1, 2025.'],
    ['Slow Moving', 'Items whose on-hand quantity exceeds or equal to two years of sales but is less than four years.'],
    ['Excessive', 'Items whose on-hand quantity exceeds or equal to four years of sales.'],
    ['Normal Goods', 'Items whose on-hand quantity is less than two years of sales.'],
    ['Coverage', 'It calculated as on-hand inventory quantity divided by average monthly sales over past 12 months.'],
  ];

  return (
    <section className="inventory-note">
      <h3>Inventory Category:</h3>
      <ul>
        {notes.map(([term, text]) => (
          <li key={term}>
            <strong>{term}:</strong> {text}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function App() {
  const [showSplash, setShowSplash] = useState(true);
  const [activeTab, setActiveTab] = useState('sales');
  const [metadata, setMetadata] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [salesFilters, setSalesFilters] = useState([]);
  const [salesSettings, setSalesSettings] = useState({ aggregation: 'monthly', currency: 'RMB', includeRevelia: true });
  const [salesData, setSalesData] = useState(null);
  const [inventoryControls, setInventoryControls] = useState({ month: '', pieSource: 'Overall', startDate: '', endDate: '', category: 'Total Inventory', source: 'Overall' });
  const [inventoryOverview, setInventoryOverview] = useState({ cards: [], pie: [] });
  const [inventoryDio, setInventoryDio] = useState({ points: [] });
  const [inventoryCoverage, setInventoryCoverage] = useState({ pie: [] });

  const uploadLabel = metadata ? 'Replace uploaded files' : 'Upload your Excel sources';

  const salesReady = Boolean(metadata?.salesLoaded && salesFilters.length > 0);
  const inventoryReady = Boolean(metadata?.inventoryLoaded);

  async function handleUpload(event) {
    const files = Array.from(event.target.files || []);
    if (!files.length) {
      return;
    }

    setLoading(true);
    setError('');
    try {
      const response = await uploadFiles(files);
      startTransition(() => {
        setMetadata(response);
        setSalesFilters([buildDefaultFilter(response, 'Filter 1')]);
        setInventoryControls({
          month: response.inventoryFilters?.defaultMonth || '',
          pieSource: 'Overall',
          startDate: response.inventoryFilters?.defaultStart || '',
          endDate: response.inventoryFilters?.defaultEnd || '',
          category: 'Total Inventory',
          source: 'Overall',
        });
        setActiveTab(response.salesLoaded ? 'sales' : 'inventory');
      });
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setLoading(false);
      event.target.value = '';
    }
  }

  useEffect(() => {
    if (!salesReady) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    postJson('/api/sales/dashboard', {
      aggregation: salesSettings.aggregation,
      currency: salesSettings.currency,
      includeRevelia: salesSettings.includeRevelia,
      filters: salesFilters,
    })
      .then((response) => {
        if (!cancelled) {
          startTransition(() => setSalesData(response));
        }
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(requestError.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [salesReady, salesFilters, salesSettings]);

  useEffect(() => {
    if (!inventoryReady || activeTab !== 'inventory') {
      return;
    }

    let cancelled = false;
    setLoading(true);
    Promise.all([
      postJson('/api/inventory/overview', {
        month: inventoryControls.month,
        pieSource: inventoryControls.pieSource,
      }),
      postJson('/api/inventory/dio', {
        startDate: inventoryControls.startDate,
        endDate: inventoryControls.endDate,
        category: inventoryControls.category,
      }),
      postJson('/api/inventory/coverage', {
        month: inventoryControls.month,
        source: inventoryControls.source,
      }),
    ])
      .then(([overview, dio, coverage]) => {
        if (!cancelled) {
          startTransition(() => {
            setInventoryOverview(overview);
            setInventoryDio(dio);
            setInventoryCoverage(coverage);
          });
        }
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(requestError.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeTab, inventoryControls, inventoryReady]);

  const salesFigures = useMemo(() => {
    if (!salesData) {
      return null;
    }

    const currencyLabel = salesSettings.currency === 'EUR' ? 'EUR' : salesSettings.currency === 'USD' ? 'USD' : 'RMB';
    return {
      salesAmount: buildSeriesFigure(salesData.salesAmount, 'Gross Sales Amount', `Gross Sales (${currencyLabel})`, salesSettings.aggregation),
      salesQuantity: buildSeriesFigure(salesData.salesQuantity, 'Sales Quantity', 'Quantity', salesSettings.aggregation),
      unitPrice: buildSeriesFigure(salesData.unitPrice, 'Unit Price', `Unit Price (${currencyLabel})`, salesSettings.aggregation),
      ebitPercent: buildSeriesFigure(salesData.ebitPercent, 'EBIT %', 'EBIT %', salesSettings.aggregation, '%{y:.2%}', true, (value) => (value == null ? '' : `${(value * 100).toFixed(2)}%`)),
    };
  }, [salesData, salesSettings]);

  if (showSplash) {
    return (
      <div className="splash-screen">
        <video
          className="splash-video"
          src={launchVideo}
          autoPlay
          muted
          playsInline
          onEnded={() => setShowSplash(false)}
          onError={() => setShowSplash(false)}
        />
        <button type="button" className="splash-skip" onClick={() => setShowSplash(false)}>
          Skip
        </button>
      </div>
    );
  }

  if (!metadata) {
    return (
      <main className="launch-upload-page">
        <label className={loading ? 'launch-upload-target loading' : 'launch-upload-target'}>
          <input type="file" multiple accept=".xls,.xlsx" onChange={handleUpload} />
          <img src={bremboLogoTransparent} alt="Brembo" className="launch-upload-logo" />
          <span>{loading ? 'Uploading files...' : 'Click the Brembo logo to upload files'}</span>
        </label>
        {error ? <div className="launch-error">{error}</div> : null}
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <img src={bremboLogo} alt="Brembo" className="brand-logo" />
        </div>

        <label className="upload-panel">
          <span>{uploadLabel}</span>
          <input type="file" multiple accept=".xls,.xlsx" onChange={handleUpload} />
          <strong>{loading ? 'Working...' : 'Choose files'}</strong>
        </label>

        <div className="tab-row">
          <button type="button" className={activeTab === 'sales' ? 'tab active' : 'tab'} onClick={() => setActiveTab('sales')} disabled={!metadata?.salesLoaded}>
            Sales
          </button>
          <button type="button" className={activeTab === 'inventory' ? 'tab active' : 'tab'} onClick={() => setActiveTab('inventory')} disabled={!metadata?.inventoryLoaded}>
            Inventory
          </button>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}

        {activeTab === 'sales' && metadata?.salesLoaded ? (
          <>
            <section className="control-panel">
              <h2 className="sidebar-title">Sales Controls</h2>
              <div className="control-row compact-row">
                <SearchableSelectField
                  label="Aggregation"
                  options={[
                    { label: 'Monthly', value: 'monthly' },
                    { label: 'Yearly', value: 'yearly' },
                  ]}
                  value={salesSettings.aggregation}
                  onChange={(aggregation) => setSalesSettings((current) => ({ ...current, aggregation }))}
                />
                <SearchableSelectField
                  label="Currency"
                  options={['RMB', 'EUR', 'USD']}
                  value={salesSettings.currency}
                  onChange={(currency) => setSalesSettings((current) => ({ ...current, currency }))}
                />
              </div>
              <label className="toggle-row">
                <input type="checkbox" checked={salesSettings.includeRevelia} onChange={(event) => setSalesSettings((current) => ({ ...current, includeRevelia: event.target.checked }))} />
                <span>Include Revelia</span>
              </label>
              <button
                type="button"
                className="primary-button"
                disabled={salesFilters.length >= 2}
                onClick={() => setSalesFilters((current) => [...current, buildDefaultFilter(metadata, `Filter ${current.length + 1}`)])}
              >
                Add Comparison Filter
              </button>
            </section>
            <section className="sidebar-filters">
              {salesFilters.map((filter, index) => (
                <FilterCard
                  key={filter.label}
                  title={filter.label}
                  filter={filter}
                  metadata={metadata}
                  removable={index > 0}
                  onRemove={() => setSalesFilters((current) => current.filter((item) => item.label !== filter.label))}
                  onChange={(nextFilter) => setSalesFilters((current) => current.map((item) => (item.label === filter.label ? nextFilter : item)))}
                />
              ))}
            </section>
          </>
        ) : null}

        {activeTab === 'inventory' && metadata?.inventoryLoaded ? (
          <section className="control-panel">
            <h2 className="sidebar-title">Inventory Controls</h2>
            <SearchableSelectField
              label="Overview Month"
              options={metadata.inventoryFilters?.months || []}
              value={inventoryControls.month}
              onChange={(month) => setInventoryControls((current) => ({ ...current, month }))}
            />
            <div className="control-row compact-row">
              <SearchableSelectField
                label="Start Date"
                options={metadata.inventoryFilters?.months || []}
                value={inventoryControls.startDate}
                onChange={(startDate) => setInventoryControls((current) => ({ ...current, startDate }))}
              />
              <SearchableSelectField
                label="End Date"
                options={metadata.inventoryFilters?.months || []}
                value={inventoryControls.endDate}
                onChange={(endDate) => setInventoryControls((current) => ({ ...current, endDate }))}
              />
            </div>
            <SearchableSelectField
              label="Category"
              options={INVENTORY_CATEGORIES}
              value={inventoryControls.category}
              onChange={(category) => setInventoryControls((current) => ({ ...current, category }))}
            />
            <SearchableSelectField
              label="Inventory Category Breakdown"
              options={PIE_SOURCES}
              value={inventoryControls.pieSource}
              onChange={(pieSource) => setInventoryControls((current) => ({ ...current, pieSource }))}
            />
            <SearchableSelectField
              label="Normal Coverage Breakdown"
              options={COVERAGE_SOURCES}
              value={inventoryControls.source}
              onChange={(source) => setInventoryControls((current) => ({ ...current, source }))}
            />
            <InventoryNote />
          </section>
        ) : null}
      </aside>

      <main className="main-stage">
        {activeTab === 'sales' && metadata?.salesLoaded ? (
          <>
            {salesFigures ? (
              <section className="chart-grid">
                <article className="panel chart-panel">
                  <Plot {...salesFigures.unitPrice} useResizeHandler className="plot" />
                </article>
                <article className="panel chart-panel">
                  <Plot {...salesFigures.salesQuantity} useResizeHandler className="plot" />
                </article>
                <article className="panel chart-panel">
                  <Plot {...salesFigures.salesAmount} useResizeHandler className="plot" />
                </article>
              </section>
            ) : null}

            <section className="sales-lower-grid">
              {salesFigures ? (
                <article className="panel chart-panel">
                  <Plot {...salesFigures.ebitPercent} useResizeHandler className="plot" />
                </article>
              ) : null}
              {salesData?.costBreakdowns?.length ? (
                <article className="panel chart-panel">
                  <Plot {...buildCostBreakdownFigure(salesData.costBreakdowns)} useResizeHandler className="plot" />
                </article>
              ) : null}
            </section>
          </>
        ) : null}

        {activeTab === 'inventory' && metadata?.inventoryLoaded ? (
          <>
            <section className="inventory-overview">
              <h2>Inventory Balance Overview</h2>
              <div className="inventory-grid">
                {(inventoryOverview.cards || []).map((card) => (
                  <InventoryCard key={card.title} {...card} />
                ))}
              </div>
            </section>
            <section className="chart-grid inventory-charts">
              <article className="panel chart-panel">
                <Plot {...buildDioFigure(inventoryDio.points || [])} useResizeHandler className="plot" />
              </article>
              <article className="panel chart-panel">
                <Plot
                  {...buildInventoryPieFigure(
                    inventoryOverview.pie || [],
                    `${inventoryControls.pieSource} Inventory Category Breakdown`,
                  )}
                  useResizeHandler
                  className="plot"
                />
              </article>
              <article className="panel chart-panel">
                <Plot
                  {...buildInventoryPieFigure(
                    inventoryCoverage.pie || [],
                    `${inventoryControls.source} Normal Coverage Breakdown`,
                  )}
                  useResizeHandler
                  className="plot"
                />
              </article>
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}
