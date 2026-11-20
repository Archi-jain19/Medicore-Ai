import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { AlertCircle, Clock, Globe, LocateFixed, MapPin, Navigation, Phone, Search, Siren } from 'lucide-react'
import { EmptyState, PageHeader } from '@/components/common'
import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/input'
import { Skeleton, Spinner, Tabs, TabsList, TabsTrigger } from '@/components/ui/misc'
import { cn } from '@/lib/utils'
import { api, errorMessage } from '@/services/api'
import type { LocationsResponse, Place, PlaceCategory } from '@/types/api'

const KIND_COLOR: Record<PlaceCategory, string> = { hospital: '#b42318', pharmacy: '#0d9488', clinic: '#1e3a5f' }
const RADII = [1000, 2000, 5000, 10000, 25000]

// eslint-disable-next-line react-refresh/only-export-components
export function formatDistance(m: number) {
  return m < 1000 ? `${m} m` : `${(m / 1000).toFixed(m < 10_000 ? 1 : 0)} km`
}

function Recenter({ lat, lon, zoom }: { lat: number; lon: number; zoom: number }) {
  const map = useMap()
  useEffect(() => {
    map.setView([lat, lon], zoom)
  }, [lat, lon, zoom, map])
  return null
}

function PlaceDetails({ p }: { p: Place }) {
  return (
    <div className="space-y-1.5 text-sm">
      {p.address && (
        <p className="flex gap-1.5 text-muted-foreground">
          <MapPin className="mt-0.5 size-3.5 shrink-0" /> {p.address}
        </p>
      )}
      {p.opening_hours && (
        <p className="flex gap-1.5 text-muted-foreground">
          <Clock className="mt-0.5 size-3.5 shrink-0" /> {p.opening_hours}
        </p>
      )}
      <div className="flex flex-wrap gap-2 pt-1">
        {p.phone && (
          <Button size="sm" variant="outline" asChild>
            <a href={`tel:${p.phone.split(';')[0].replace(/\s/g, '')}`}>
              <Phone /> {p.phone.split(';')[0]}
            </a>
          </Button>
        )}
        {p.website && (
          <Button size="sm" variant="outline" asChild>
            <a href={p.website} target="_blank" rel="noreferrer">
              <Globe /> Website
            </a>
          </Button>
        )}
        <Button size="sm" variant="teal" asChild>
          <a href={p.directions_url} target="_blank" rel="noreferrer">
            <Navigation /> Directions
          </a>
        </Button>
      </div>
    </div>
  )
}

export default function Locator() {
  const [params] = useSearchParams()
  const initialCategory = (['hospital', 'clinic', 'pharmacy'] as const).find((c) => c === params.get('category'))
  const [category, setCategory] = useState<PlaceCategory>(initialCategory ?? 'hospital')
  const [radius, setRadius] = useState(5000)
  const [query, setQuery] = useState('')
  const [origin, setOrigin] = useState<{ lat: number; lon: number } | { q: string } | null>(null)
  const [data, setData] = useState<LocationsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [locating, setLocating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    if (!origin) return
    let cancelled = false
    setLoading(true)
    setError(null)
    const params = 'q' in origin ? { q: origin.q } : { lat: origin.lat, lon: origin.lon }
    api
      .get<LocationsResponse>('/locations', { params: { ...params, category, radius_m: radius } })
      .then((r) => {
        if (cancelled) return
        setData(r.data)
        setSelected(null)
      })
      .catch((e) => !cancelled && setError(errorMessage(e)))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [origin, category, radius])

  const useMyLocation = () => {
    if (!('geolocation' in navigator)) {
      setError('Your browser cannot share your location. Please type a city or address instead.')
      return
    }
    setLocating(true)
    setError(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false)
        setOrigin({ lat: pos.coords.latitude, lon: pos.coords.longitude })
      },
      (err) => {
        setLocating(false)
        setError(err.code === err.PERMISSION_DENIED ? 'Location sharing is turned off. Please type a city or address instead.' : 'We could not find your location. Please type a city or address instead.')
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 },
    )
  }

  const center = data?.center
  const zoom = radius <= 2000 ? 15 : radius <= 5000 ? 13 : radius <= 10000 ? 12 : 11

  return (
    <>
      <PageHeader
        title="Find Care Nearby"
        description="Find hospitals, clinics and pharmacies close to you. We use your location only to search, and we do not save it."
      />
      <Alert variant="destructive" className="mb-4">
        <Siren />
        <span className="text-sm">
          <strong>In an emergency, call your local emergency number</strong> (for example 911, 112, 999 or 108) instead of searching here.
        </span>
      </Alert>

      <Card className="mb-4">
        <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center">
          <Tabs value={category} onValueChange={(v) => setCategory(v as PlaceCategory)}>
            <TabsList>
              <TabsTrigger value="hospital">Hospitals</TabsTrigger>
              <TabsTrigger value="clinic">Clinics</TabsTrigger>
              <TabsTrigger value="pharmacy">Pharmacies</TabsTrigger>
            </TabsList>
          </Tabs>
          <form
            className="flex flex-1 gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              if (query.trim().length >= 2) setOrigin({ q: query.trim() })
            }}
          >
            <label htmlFor="place" className="sr-only">
              Place or address
            </label>
            <Input id="place" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Type a city or address" maxLength={120} />
            <Button type="submit" variant="outline" disabled={query.trim().length < 2} aria-label="Search place">
              <Search />
            </Button>
          </form>
          <div className="flex gap-2">
            <label htmlFor="radius" className="sr-only">
              How far to look
            </label>
            <Select id="radius" value={radius} onChange={(e) => setRadius(Number(e.target.value))} className="w-28">
              {RADII.map((r) => (
                <option key={r} value={r}>
                  {formatDistance(r)}
                </option>
              ))}
            </Select>
            <Button onClick={useMyLocation} disabled={locating}>
              {locating ? <Spinner /> : <LocateFixed />} Use my location
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertCircle />
          <span>{error}</span>
        </Alert>
      )}

      {!origin ? (
        <Card>
          <CardContent className="p-6">
            <EmptyState icon={MapPin} title="Where should we look?" body="Tap “Use my location”, or type a city or address, to see places close by." />
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
          <Card className="overflow-hidden">
            {center ? (
              <MapContainer center={[center.lat, center.lon]} zoom={zoom} className="h-[420px] w-full lg:h-[620px]" scrollWheelZoom>
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                  url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                <Recenter lat={center.lat} lon={center.lon} zoom={zoom} />
                <CircleMarker center={[center.lat, center.lon]} radius={7} pathOptions={{ color: '#2563eb', fillOpacity: 0.9 }}>
                  <Popup>You are here</Popup>
                </CircleMarker>
                {data?.places.map((p) => (
                  <CircleMarker
                    key={p.id}
                    center={[p.lat, p.lon]}
                    radius={selected === p.id ? 10 : 7}
                    pathOptions={{ color: KIND_COLOR[p.kind], fillOpacity: 0.75, weight: selected === p.id ? 3 : 1.5 }}
                    eventHandlers={{ click: () => setSelected(p.id) }}
                  >
                    <Popup>
                      <p className="font-semibold">{p.name}</p>
                      <p className="text-xs">{formatDistance(p.distance_m)} away</p>
                    </Popup>
                  </CircleMarker>
                ))}
              </MapContainer>
            ) : (
              <Skeleton className="h-[420px] w-full rounded-none lg:h-[620px]" />
            )}
          </Card>

          <Card className="flex max-h-[620px] flex-col">
            <div className="flex items-center justify-between border-b px-4 py-3 text-sm">
              <span className="font-medium">{loading ? 'Searching…' : `${data?.count ?? 0} ${data?.count === 1 ? 'place' : 'places'} found`}</span>
              {data?.place && <span className="truncate pl-2 text-xs text-muted-foreground">near {data.place.display_name.split(',')[0]}</span>}
            </div>
            <div className="flex-1 overflow-y-auto">
              {loading && !data ? (
                <div className="space-y-2 p-4">
                  <Skeleton className="h-16" />
                  <Skeleton className="h-16" />
                </div>
              ) : data && data.places.length === 0 ? (
                <EmptyState icon={MapPin} title="No places found" body="Try looking further away, or pick a different type of place. Our map has more detail in some areas than others." />
              ) : (
                <ul className="divide-y">
                  {data?.places.map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => setSelected(selected === p.id ? null : p.id)}
                        className={cn('w-full px-4 py-3 text-left hover:bg-secondary/60', selected === p.id && 'bg-accent/50')}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span className="font-medium">{p.name}</span>
                          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{formatDistance(p.distance_m)}</span>
                        </div>
                        <div className="mt-1 flex gap-1.5">
                          <Badge variant="outline">{p.kind}</Badge>
                          {p.emergency === 'yes' && <Badge variant="destructive">Has an emergency room</Badge>}
                        </div>
                      </button>
                      {selected === p.id && (
                        <div className="px-4 pb-3">
                          <PlaceDetails p={p} />
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {data?.note && <p className="border-t bg-warning/10 px-4 py-2 text-xs">{data.note}</p>}
            {data && <p className="border-t px-4 py-2 text-[11px] text-muted-foreground">{data.attribution}</p>}
          </Card>
        </div>
      )}
    </>
  )
}
