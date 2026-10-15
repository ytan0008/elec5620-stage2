import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Chart } from '../api'

const COLORS = ['#3ef0ff', '#ff4fd8', '#ffd34d', '#b8ff5c', '#ff8a3d']
const axis = { stroke: '#b9b0e0', fontFamily: 'Pixelify Sans', fontSize: 13 }

export default function ChartView({ chart }: { chart: Chart }) {
  const rows = chart.categories.map((category, i) => Object.fromEntries([['name', category], ...chart.series.map(series => [series.name, series.values[i]])]))
  return <figure className="tile p-4" aria-label={chart.title}>
    <figcaption className="mb-3 text-center font-pixel text-moon">{chart.title}{chart.unit && chart.type !== 'pie' ? ` (${chart.unit})` : ''}</figcaption>
    {chart.type === 'pie' ? <div className="grid gap-4 sm:grid-cols-2">{chart.series.map(series => <div key={series.name} className="h-56">
      <p className="text-center font-pixel text-cyan">{series.name}</p>
      <ResponsiveContainer width="100%" height="90%"><PieChart>
        <Pie data={chart.categories.map((name, i) => ({ name, value: series.values[i] }))} dataKey="value" nameKey="name" outerRadius="80%" label={({ name, value }) => `${name} ${value}%`} labelLine={false} stroke="#0d0a24" strokeWidth={3} isAnimationActive={false}>
          {chart.categories.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
        </Pie><Tooltip />
      </PieChart></ResponsiveContainer>
    </div>)}</div> : <div className="h-72"><ResponsiveContainer width="100%" height="100%">
      {chart.type === 'line'
        ? <LineChart data={rows}><CartesianGrid stroke="#3a2b7e" strokeDasharray="4 4" /><XAxis dataKey="name" {...axis} /><YAxis {...axis} /><Tooltip /><Legend wrapperStyle={{ fontFamily: 'Pixelify Sans' }} />
          {chart.series.map((series, i) => <Line key={series.name} dataKey={series.name} stroke={COLORS[i % COLORS.length]} strokeWidth={3} dot={{ r: 4, strokeWidth: 0, fill: COLORS[i % COLORS.length] }} type="linear" isAnimationActive={false} />)}</LineChart>
        : <BarChart data={rows}><CartesianGrid stroke="#3a2b7e" strokeDasharray="4 4" /><XAxis dataKey="name" {...axis} /><YAxis {...axis} /><Tooltip cursor={{ fill: 'rgba(107,82,214,.2)' }} /><Legend wrapperStyle={{ fontFamily: 'Pixelify Sans' }} />
          {chart.series.map((series, i) => <Bar key={series.name} dataKey={series.name} fill={COLORS[i % COLORS.length]} isAnimationActive={false} />)}</BarChart>}
    </ResponsiveContainer></div>}
  </figure>
}
