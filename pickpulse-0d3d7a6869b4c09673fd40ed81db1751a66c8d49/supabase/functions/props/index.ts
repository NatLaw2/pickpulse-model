import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// UI sport keys to Odds API sport keys mapping
const SPORT_MAPPING: Record<string, string> = {
  nba: 'basketball_nba',
  mlb: 'baseball_mlb',
  nhl: 'icehockey_nhl',
  ncaab: 'basketball_ncaab',
  ncaaf: 'americanfootball_ncaaf',
  nfl: 'americanfootball_nfl',
};

// Default player prop markets by sport
const DEFAULT_PROP_MARKETS: Record<string, string[]> = {
  nba: ['player_points', 'player_rebounds', 'player_assists', 'player_threes'],
  mlb: ['batter_hits', 'batter_runs', 'batter_rbis', 'pitcher_strikeouts'],
  nhl: ['player_goals', 'player_assists', 'player_shots_on_goal'],
  ncaab: ['player_points', 'player_rebounds', 'player_assists'],
  ncaaf: ['player_pass_tds', 'player_rush_yds', 'player_reception_yds'],
  nfl: ['player_pass_tds', 'player_rush_yds', 'player_reception_yds', 'player_anytime_td'],
};

interface PropOutcome {
  name: string;
  description?: string;
  price: number;
  point?: number;
}

interface PropMarket {
  key: string;
  outcomes: PropOutcome[];
}

interface TransformedProp {
  market: string;
  marketLabel: string;
  props: Array<{
    player: string;
    line: number | null;
    over: number | null;
    under: number | null;
  }>;
}

function getMarketLabel(marketKey: string): string {
  const labels: Record<string, string> = {
    player_points: 'Points',
    player_rebounds: 'Rebounds',
    player_assists: 'Assists',
    player_threes: 'Three Pointers',
    batter_hits: 'Hits',
    batter_runs: 'Runs',
    batter_rbis: 'RBIs',
    pitcher_strikeouts: 'Strikeouts',
    player_goals: 'Goals',
    player_shots_on_goal: 'Shots on Goal',
    player_pass_tds: 'Passing TDs',
    player_rush_yds: 'Rushing Yards',
    player_reception_yds: 'Receiving Yards',
    player_anytime_td: 'Anytime TD',
  };
  return labels[marketKey] || marketKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function transformProps(bookmakers: any[], markets: string[]): TransformedProp[] {
  // Find best bookmaker
  const preferredBooks = ['fanduel', 'draftkings', 'betmgm'];
  const bookmaker = bookmakers.find(b => preferredBooks.includes(b.key)) || bookmakers[0];
  
  if (!bookmaker) return [];
  
  const results: TransformedProp[] = [];
  
  for (const marketKey of markets) {
    const market = bookmaker.markets?.find((m: any) => m.key === marketKey);
    if (!market) continue;
    
    // Group outcomes by player
    const playerMap = new Map<string, { line: number | null; over: number | null; under: number | null }>();
    
    for (const outcome of market.outcomes) {
      const playerName = outcome.description || outcome.name;
      if (!playerMap.has(playerName)) {
        playerMap.set(playerName, { line: null, over: null, under: null });
      }
      
      const entry = playerMap.get(playerName)!;
      if (outcome.point !== undefined) {
        entry.line = outcome.point;
      }
      
      if (outcome.name.toLowerCase() === 'over') {
        entry.over = outcome.price;
      } else if (outcome.name.toLowerCase() === 'under') {
        entry.under = outcome.price;
      }
    }
    
    const props = Array.from(playerMap.entries()).map(([player, data]) => ({
      player,
      ...data,
    }));
    
    if (props.length > 0) {
      results.push({
        market: marketKey,
        marketLabel: getMarketLabel(marketKey),
        props,
      });
    }
  }
  
  return results;
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }
  
  try {
    const url = new URL(req.url);
    const sportKey = url.searchParams.get('sportKey');
    const eventId = url.searchParams.get('eventId');
    const marketsParam = url.searchParams.get('markets');
    
    if (!sportKey || !eventId) {
      return new Response(
        JSON.stringify({ error: 'sportKey and eventId are required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }
    
    const ODDS_API_KEY = Deno.env.get('ODDS_API_KEY');
    if (!ODDS_API_KEY) {
      throw new Error('ODDS_API_KEY not configured');
    }
    
    const apiSport = SPORT_MAPPING[sportKey];
    if (!apiSport) {
      return new Response(
        JSON.stringify({ error: 'Invalid sport key' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }
    
    // Determine which markets to fetch
    const markets = marketsParam 
      ? marketsParam.split(',')
      : DEFAULT_PROP_MARKETS[sportKey] || [];
    
    const marketsQuery = markets.join(',');
    
    const apiUrl = `https://api.the-odds-api.com/v4/sports/${apiSport}/events/${eventId}/odds?apiKey=${ODDS_API_KEY}&regions=us&markets=${marketsQuery}&oddsFormat=american`;
    
    const response = await fetch(apiUrl);
    
    if (!response.ok) {
      if (response.status === 404) {
        return new Response(
          JSON.stringify({ props: [], message: 'No props available for this event' }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        );
      }
      throw new Error(`Odds API returned ${response.status}`);
    }
    
    const data = await response.json();
    const transformedProps = transformProps(data.bookmakers || [], markets);
    
    return new Response(
      JSON.stringify({ props: transformedProps }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (error: unknown) {
    console.error('Props API error:', error);
    const message = error instanceof Error ? error.message : 'Internal server error';
    return new Response(
      JSON.stringify({ error: message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
