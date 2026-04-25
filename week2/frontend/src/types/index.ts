/* Types matching backend Pydantic models. */

export type TravelStyle =
  | 'adventure'
  | 'spiritual'
  | 'cultural'
  | 'relaxation'
  | 'party'
  | 'nature'
  | 'luxury'
  | 'backpacking'
  | 'family'
  | 'romantic';

export type TravelerType = 'solo' | 'couple' | 'family' | 'group' | 'business';

export interface TripRequest {
  destination: string;
  origin: string;
  start_date?: string;
  end_date?: string;
  duration_days: number;
  budget: number;
  currency: string;
  traveler_type: TravelerType;
  traveler_count: number;
  styles: TravelStyle[];
  interests: string[];
  constraints: string[];
}

export type TripStatusType =
  | 'collecting_preferences'
  | 'researching'
  | 'checkpoint_1'
  | 'planning'
  | 'checkpoint_2'
  | 'verifying'
  | 'checkpoint_3'
  | 'finalizing'
  | 'complete'
  | 'replanning'
  | 'error';

export interface PlanOption {
  id: string;
  label: string;
  style: string;
  estimated_total: number;
  currency: string;
  highlights: string[];
  trade_offs: string;
  is_recommended: boolean;
  transport_mode?: string;   // "flight" | "train" | "bus"
  transport_name?: string;   // e.g. "Air India" or "AC 3 Tier"
  hotel_name?: string;       // e.g. "Hotel Himalaya"
  airport_transfer?: string; // e.g. "Bus from Kochi → Munnar"
}

export interface Activity {
  name: string;
  description: string;
  time_slot: { start: string; end: string };
  category: string;
  cost: number;
  currency: string;
  place_id?: string;
  address?: string;
  location?: string;
  latitude?: number;
  longitude?: number;
  rating?: number;
  booking_url?: string;
  is_verified: boolean;
}

export interface MealSuggestion {
  meal_type: string;
  name?: string;
  suggestion?: string;
  cost_estimate?: number;
  estimated_cost?: number;
}

export interface DayPlan {
  day_number: number;
  title: string;
  description?: string;
  activities: Activity[];
  transport?: TransportLeg[];
  meals: MealSuggestion[];
  day_cost?: number;
  estimated_cost?: number;
  weather_summary?: string;
}

export interface Itinerary {
  destination: string;
  duration_days: number;
  days: DayPlan[];
  transport: TransportLeg[];
  selected_hotel?: Record<string, any>;
  selected_flight?: Record<string, any>;
  total_cost: number;
  currency: string;
}

export interface TransportLeg {
  mode: string;
  from_location: string;
  to_location: string;
  departure_time?: string;
  arrival_time?: string;
  duration_minutes?: number;
  cost: number;
  currency: string;
  provider?: string;
  booking_url?: string;
  notes?: string;
}

export interface BudgetBreakdown {
  transport: number;
  accommodation: number;
  food: number;
  activities: number;
  buffer: number;
  currency: string;
  total?: number;
  traveler_count?: number;
  per_person_total?: number;
}

export interface BookingItem {
  type: string;
  name: string;
  cost: number;
  currency: string;
  booking_url?: string;
  provider?: string;
}

export interface BookingCart {
  items: BookingItem[];
  total: number;
  currency: string;
}

export interface MapMarker {
  name: string;
  lat: number;
  lng: number;
  day?: number;
  type?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
  data?: any;
}

export interface TripUnderstanding {
  traveler_type: string;
  styles: string;
  budget: number;
  currency: string;
  origin: string;
  destination: string;
  duration_days: number;
  start_date: string;
  end_date: string;
  traveler_count: number;
  interests: string[];
}

export interface BookingOption {
  category: 'travel' | 'stay' | 'activity';
  icon: string;
  name: string;
  route?: string;
  mode?: string;
  cost: number;
  cost_per_night?: number;
  nights?: number;
  currency: string;
  location?: string;
  rating?: number;
  day?: number;
  details: string[];
  booking_url?: string;
  place_id?: string;
}

export interface CheckpointData {
  type: string;
  checkpoint_id: string;
  options: string[];
  trip_understanding?: TripUnderstanding;
  research_summary?: Record<string, any>;
  budget_feasibility?: Record<string, any>;
  plan_options?: PlanOption[];
  budget_breakdown?: BudgetBreakdown;
  itinerary?: Itinerary;
  booking_options?: BookingOption[];
  booking_total?: number;
  verification_results?: Record<string, any>[];
  price_changes?: PriceChange[];
  travel_advisory?: Record<string, any>;
  research?: ResearchData;
  recommended_transport_id?: string;
  recommended_hotel_id?: string;
}

export interface PriceChange {
  item: string;
  old_price: number;
  new_price: number;
}

export interface ResearchFlight {
  id?: string;
  airline_or_operator: string;
  price: number;
  currency: string;
  departure_time?: string;
  arrival_time?: string;
  duration?: string;
  duration_minutes?: number;
  stops?: number;
  layover_info?: string;
  source?: string;
  from_location?: string;
  to_location?: string;
  mode?: string;
  class_type?: string;
  booking_url?: string;
}

export interface ResearchHotel {
  id?: string;
  name: string;
  price_per_night: number;
  total_price?: number;
  currency: string;
  rating?: number;
  location?: string;
  amenities?: string[];
  source?: string;
  hotel_type?: string;
  image_url?: string;
  booking_url?: string;
}

export interface ResearchActivity {
  name: string;
  description?: string;
  cost?: number;
  price?: number;
  currency?: string;
  rating?: number;
  category?: string;
  location?: string;
  duration_minutes?: number;
  booking_url?: string;
  place_id?: string;
}

export interface ResearchData {
  flights: ResearchFlight[];
  trains: ResearchFlight[];
  buses: ResearchFlight[];
  hotels: ResearchHotel[];
  activities: ResearchActivity[];
}

export interface SSEEvent {
  type: string;
  data: any;
}

export interface AgentStep {
  agent: string;
  step: string;
  detail: string;
  status: 'running' | 'done' | 'warning' | 'waiting';
  substeps: string[];
  timestamp?: number;
}

export interface TripSummary {
  id: string;
  status: TripStatusType;
  destination?: string;
  created_at: string;
  is_sample: boolean;
  request_json?: string;
}

export interface TripState {
  trip_id: string;
  status: TripStatusType;
  request?: TripRequest;
  chat_history: ChatMessage[];
  itinerary?: Itinerary;
  budget_breakdown?: BudgetBreakdown;
  plan_options?: PlanOption[];
  booking_cart?: BookingCart;
  checkpoint?: CheckpointData;
  markers?: MapMarker[];
  reasoning_log?: string[];
  price_changes?: PriceChange[];
  research?: ResearchData;
  agent_step?: AgentStep;
  completed_agents?: AgentStep[];
  pending_replan?: boolean;
  error?: string;
}
