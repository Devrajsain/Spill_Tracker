import React from 'react';

export const OperationalStatistics: React.FC = () => {
  const stats = [
    {
      value: '1,248',
      label: 'CASES PROCESSED',
      subtext: 'SAR Imagery & MetOcean Hindcasts'
    },
    {
      value: '18,600+',
      label: 'VESSEL RECORDS ANALYZED',
      subtext: 'AIS Telemetry Correlated'
    },
    {
      value: '42',
      label: 'COASTAL REGIONS COVERED',
      subtext: 'EEZ & Territorial Monitored Waters'
    },
    {
      value: '24×7',
      label: 'MONITORING SUPPORT',
      subtext: 'Automated Satellite Pass Alerts'
    }
  ];

  return (
    <section className="bg-white border-b border-gov-border py-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-gov-light border border-gov-border rounded-gov p-6 sm:p-8">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8 divide-y sm:divide-y-0 sm:divide-x divide-gov-border">
            {stats.map((item, index) => (
              <div 
                key={index}
                className={`flex flex-col items-start ${index !== 0 ? 'pt-6 sm:pt-0 sm:pl-8' : ''}`}
              >
                <span className="text-3xl sm:text-4xl font-extrabold text-navy-800 font-sans tracking-tight mb-1">
                  {item.value}
                </span>
                <span className="text-xs font-bold text-gov-blue uppercase tracking-wider mb-0.5">
                  {item.label}
                </span>
                <span className="text-[11px] text-gov-muted">
                  {item.subtext}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};
