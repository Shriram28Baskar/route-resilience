"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, Users, Clock, AlertTriangle } from "lucide-react";
import {
  getGlobalResilience,
  runTimeline,
  getCentrality,
  type ResilienceScoreResponse,
  type TimelineStep,
} from "@/lib/api";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";

export default function AnalyticsPage() {
  const [resilience, setResilience] = useState<ResilienceScoreResponse | null>(null);
  const [timeline, setTimeline] = useState<TimelineStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);

  useEffect(() => {
    getGlobalResilience()
      .then(setResilience)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleRunTimeline = async () => {
    setTimelineLoading(true);
    try {
      // Fetch top gatekeepers to use as seeds if none selected
      const cent = await getCentrality(3);
      const seeds = cent.gatekeepers.map(g => g.node_id);
      
      const res = await runTimeline(seeds, 2, 10);
      setTimeline(res.timeline_steps);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setTimelineLoading(false);
    }
  };

  const currentScore = resilience?.global_resilience_score ?? 0;
  const scoreColor = currentScore > 0.8 ? "#22C55E" : currentScore > 0.5 ? "#FFB400" : "#FF4444";
  
  const worstTimelineStep = timeline.length > 0 
    ? timeline.reduce((prev, current) => (prev.isolated_population > current.isolated_population) ? prev : current)
    : null;

  return (
    <div className="min-h-screen bg-[#0B0F1A] p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        
        {/* Header */}
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-[#00E5B4]/10 flex items-center justify-center">
              <Activity className="w-4 h-4 text-[#00E5B4]" />
            </div>
            <h1 className="font-display text-2xl font-bold">Advanced Analytics</h1>
          </div>
          <p className="text-[#6B7280] text-sm">
            Global network resilience, population impact, and disaster timeline modeling.
          </p>
        </div>

        {error && (
          <div className="bg-[#FF4444]/10 border border-[#FF4444]/20 rounded-xl p-4 text-[#FF4444] text-xs">
            {error}
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-6">
          
          {/* Global Resilience Score */}
          <div className="bg-[#111827] border border-white/8 rounded-xl p-6 flex flex-col justify-center items-center relative overflow-hidden">
             <div className="absolute top-0 left-0 w-full h-1" style={{ background: scoreColor }} />
             <h2 className="font-display font-semibold text-sm mb-4 uppercase tracking-widest text-[#6B7280] self-start">Global Resilience Score</h2>
             
             {loading ? (
               <div className="h-32 w-32 rounded-full border-4 border-white/10 animate-pulse" />
             ) : (
               <div className="text-center">
                 <div className="text-6xl font-display font-bold mb-2" style={{ color: scoreColor }}>
                   {(currentScore * 100).toFixed(1)}<span className="text-2xl text-[#6B7280]">%</span>
                 </div>
                 <div className="text-sm text-[#6B7280]">
                    Based on LCC connectivity and network density.
                 </div>
               </div>
             )}
          </div>

          {/* Population Impact Summary */}
          <div className="bg-[#111827] border border-white/8 rounded-xl p-6">
             <h2 className="font-display font-semibold text-sm mb-4 uppercase tracking-widest text-[#6B7280] flex items-center gap-2">
               <Users className="w-4 h-4" /> Population Impact
             </h2>
             
             <div className="space-y-4">
                <div className="p-4 bg-[#0B0F1A] rounded-lg border border-white/5">
                  <div className="text-xs text-[#6B7280] mb-1">Estimated Base Population</div>
                  <div className="text-2xl font-mono">13,600,000</div>
                </div>
                
                <div className="p-4 bg-[#FF4444]/10 border border-[#FF4444]/20 rounded-lg">
                  <div className="text-xs text-[#FF4444] mb-1 font-semibold flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> Worst-Case Isolated Population (Timeline)
                  </div>
                  <div className="text-3xl font-display font-bold text-[#FF4444]">
                    {worstTimelineStep ? worstTimelineStep.isolated_population.toLocaleString() : "Run timeline to calculate"}
                  </div>
                  {worstTimelineStep && (
                    <div className="text-xs text-[#FF4444]/80 mt-1">
                      Peak isolation hit on Day {worstTimelineStep.day} ({worstTimelineStep.phase})
                    </div>
                  )}
                </div>
             </div>
          </div>
        </div>

        {/* Disaster Timeline */}
        <div className="bg-[#111827] border border-white/8 rounded-xl p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="font-display font-semibold text-sm uppercase tracking-widest text-[#6B7280] flex items-center gap-2">
              <Clock className="w-4 h-4" /> Disaster Progression Timeline
            </h2>
            
            <button
              onClick={handleRunTimeline}
              disabled={timelineLoading}
              className="px-4 py-2 bg-[#00E5B4]/10 text-[#00E5B4] hover:bg-[#00E5B4]/20 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
            >
              {timelineLoading ? "Simulating..." : "Run Standard Scenario"}
            </button>
          </div>

          {timeline.length > 0 ? (
            <div className="space-y-6">
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={timeline} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorGrs" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#00E5B4" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#00E5B4" stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorPop" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#FF4444" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#FF4444" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                    <XAxis dataKey="day" stroke="#6B7280" fontSize={12} tickLine={false} axisLine={false} />
                    <YAxis yAxisId="left" stroke="#6B7280" fontSize={12} tickLine={false} axisLine={false} domain={[0, 1]} />
                    <YAxis yAxisId="right" orientation="right" stroke="#FF4444" fontSize={12} tickLine={false} axisLine={false} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#111827', borderColor: 'rgba(255,255,255,0.1)' }}
                      labelStyle={{ color: '#6B7280' }}
                    />
                    <Legend />
                    <Area yAxisId="left" type="monotone" dataKey="global_resilience_score" name="Resilience Score" stroke="#00E5B4" fillOpacity={1} fill="url(#colorGrs)" />
                    <Area yAxisId="right" type="step" dataKey="isolated_population" name="Isolated Pop" stroke="#FF4444" fillOpacity={1} fill="url(#colorPop)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-2 text-xs">
                {timeline.map((step) => (
                  <div key={step.day} className="p-3 bg-[#0B0F1A] rounded border border-white/5">
                    <div className="text-[#6B7280] font-semibold mb-1">Day {step.day}</div>
                    <div className="text-white truncate mb-1" title={step.phase}>{step.phase}</div>
                    <div className="flex justify-between mt-2">
                       <span className="text-[#00E5B4]">{step.global_resilience_score.toFixed(2)}</span>
                       <span className="text-[#FF4444]">{Math.round(step.isolated_population / 1000)}k</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
             <div className="py-12 text-center text-[#6B7280] bg-[#0B0F1A] rounded-lg border border-white/5 border-dashed">
               Click "Run Standard Scenario" to model a disaster striking the top gatekeeper nodes,
               cascading failures over 3 days, and subsequent recovery.
             </div>
          )}
        </div>
      </div>
    </div>
  );
}
