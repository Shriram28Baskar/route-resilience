"use client";

import { useState } from "react";
import { FileText, Download, CheckCircle, Circle } from "lucide-react";
import { generateReport } from "@/lib/api";

const REPORT_SECTIONS = [
  { id: "Global Resilience Score", label: "Global Resilience Score", desc: "Overall city connectivity and density metrics" },
  { id: "Population Impact Analysis", label: "Population Impact Analysis", desc: "Estimates of isolated populations based on current graph state" },
  { id: "Disaster Progression Timeline", label: "Disaster Progression Timeline", desc: "Day-by-day cascade and recovery modeling" },
];

export default function ReportsPage() {
  const [selectedSections, setSelectedSections] = useState<string[]>(
    REPORT_SECTIONS.map(s => s.id)
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleSection = (id: string) => {
    setSelectedSections(prev => 
      prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]
    );
  };

  const handleDownload = async () => {
    if (selectedSections.length === 0) {
      setError("Please select at least one section to include in the report.");
      return;
    }
    
    setLoading(true);
    setError(null);
    
    try {
      const blob = await generateReport("Bengaluru", selectedSections);
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Situation_Report_Bengaluru.pdf`;
      document.body.appendChild(a);
      a.click();
      
      // Cleanup
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0B0F1A] p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        
        {/* Header */}
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-[#00E5B4]/10 flex items-center justify-center">
              <FileText className="w-4 h-4 text-[#00E5B4]" />
            </div>
            <h1 className="font-display text-2xl font-bold">Situation Reports</h1>
          </div>
          <p className="text-[#6B7280] text-sm">
            Generate and download comprehensive PDF analytics reports.
          </p>
        </div>

        {error && (
          <div className="bg-[#FF4444]/10 border border-[#FF4444]/20 rounded-xl p-4 text-[#FF4444] text-sm">
            {error}
          </div>
        )}

        <div className="bg-[#111827] border border-white/8 rounded-xl overflow-hidden">
          <div className="p-6 border-b border-white/8">
            <h2 className="font-display font-semibold text-lg mb-4">Report Configuration</h2>
            
            <div className="space-y-3">
               <h3 className="text-xs font-semibold uppercase tracking-wider text-[#6B7280]">Include Sections</h3>
               
               <div className="space-y-2">
                 {REPORT_SECTIONS.map(section => {
                   const isSelected = selectedSections.includes(section.id);
                   return (
                     <div 
                       key={section.id} 
                       onClick={() => toggleSection(section.id)}
                       className={`flex items-start gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
                         isSelected 
                           ? "bg-[#00E5B4]/5 border-[#00E5B4]/30" 
                           : "bg-[#0B0F1A] border-white/5 hover:border-white/20"
                       }`}
                     >
                       <div className="mt-0.5">
                         {isSelected ? (
                           <CheckCircle className="w-5 h-5 text-[#00E5B4]" />
                         ) : (
                           <Circle className="w-5 h-5 text-[#6B7280]" />
                         )}
                       </div>
                       <div>
                         <div className={`font-medium ${isSelected ? "text-white" : "text-gray-300"}`}>
                           {section.label}
                         </div>
                         <div className="text-sm text-[#6B7280] mt-1">
                           {section.desc}
                         </div>
                       </div>
                     </div>
                   );
                 })}
               </div>
            </div>

            {/* Removed Features (As per requirement 4: Future Scope) */}
            <div className="mt-8 space-y-3">
               <h3 className="text-xs font-semibold uppercase tracking-wider text-[#6B7280]">Future Scope (Disabled)</h3>
               
               <div className="flex items-start gap-3 p-4 rounded-lg border border-red-500/20 bg-red-500/5 opacity-60">
                 <div className="mt-0.5 flex items-center justify-center w-5 h-5 rounded-full border border-red-500">
                   <div className="w-3 h-0.5 bg-red-500" style={{ transform: "rotate(45deg)" }} />
                 </div>
                 <div>
                   <div className="font-medium text-red-400 line-through">
                     Multi-City Benchmarking
                   </div>
                   <div className="text-sm text-[#6B7280] mt-1">
                     Disabled as per hackathon scope changes.
                   </div>
                 </div>
               </div>
            </div>
          </div>

          <div className="p-6 bg-[#161F33] flex justify-between items-center">
            <div className="text-sm text-[#6B7280]">
               Target AOI: <span className="text-white font-mono">Bengaluru, India</span>
            </div>
            
            <button
              onClick={handleDownload}
              disabled={loading || selectedSections.length === 0}
              className="flex items-center gap-2 px-6 py-2.5 bg-[#00E5B4] text-[#0B0F1A] font-semibold rounded-lg hover:bg-[#00B38A] transition-colors disabled:opacity-50"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-[#0B0F1A]/30 border-t-[#0B0F1A] rounded-full animate-spin" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              {loading ? "Generating PDF..." : "Generate Report"}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
