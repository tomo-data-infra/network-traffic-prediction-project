cube(`Targets`, {
  sql: `SELECT * FROM public.targets`,

  dimensions: {
    id: {
      sql: `id`,
      type: `number`,
      primaryKey: true
    },
    ip: {
      sql: `ip`,
      type: `string`
    },
    label: {
      sql: `label`,
      type: `string`
    }
  }
});

cube(`PingLogs`, {
  sql: `SELECT * FROM public.ping_logs`,

  joins: {
    Targets: {
      relationship: `belongsTo`,
      sql: `${PingLogs.targetId} = ${Targets.id}`
      //sql: `${CUBE.PingLogs.targetId} = ${CUBE.Targets.id}`
      //sql: `${Cubes.PingLogs.targetId} = ${Cubes.Targets.id}`
    }
  },

  measures: {
    meanRtt: {
      sql: `rtt_ms`,
      type: `avg`,
      title: `Mean RTT`
    },
    highestRtt: {
      sql: `rtt_ms`,
      type: `max`,
      title: `Highest RTT`
    },
    packetLossRate: {
      sql: `CASE WHEN is_timeout = true THEN 1 ELSE 0 END`,
      type: `avg`,
      title: `Packet Loss Rate`
    }
  },

  dimensions: {
    /*
    id: {
      sql: `id`,
      type: `number`,
      primaryKey: true
    },
    */
    compositeId: {
      sql: `CONCAT(ts, '-', target_id)`,
      type: `string`,
      primaryKey: true
    },
    targetId: {
      sql: `target_id`,
      type: `number`
    },
    ts: {
      sql: `ts`,
      type: `time`
    }
  },

  /*
  preAggregations: {
    rollupMinute: {
      type: `rollup`,
      measureReferences: [Cubes.PingLogs.meanRtt, Cubes.PingLogs.highestRtt, Cubes.PingLogs.packetLossRate],
      dimensionReferences: [Cubes.PingLogs.targetId],
      timeDimensionReference: Cubes.PingLogs.ts,
      granularity: `minute`,
      external: false,
      sql: `SELECT ts_minute as ts, target_id, mean_rtt, highest_rtt, packet_loss_rate FROM public.minute_rollups`
    },
    rollupHourly: {
      type: `rollup`,
      measureReferences: [Cubes.PingLogs.meanRtt, Cubes.PingLogs.highestRtt, Cubes.PingLogs.packetLossRate],
      dimensionReferences: [Cubes.PingLogs.targetId],
      timeDimensionReference: Cubes.PingLogs.ts,
      granularity: `hour`,
      external: false,
      sql: `SELECT ts_hour as ts, target_id, mean_rtt, highest_rtt, packet_loss_rate FROM public.hourly_rollups`
    },
    rollupDaily: {
      type: `rollup`,
      measureReferences: [Cubes.PingLogs.meanRtt, Cubes.PingLogs.highestRtt, Cubes.PingLogs.packetLossRate],
      dimensionReferences: [Cubes.PingLogs.targetId],
      timeDimensionReference: Cubes.PingLogs.ts,
      granularity: `day`,
      external: false,
      sql: `SELECT ts_day as ts, target_id, mean_rtt, highest_rtt, packet_loss_rate FROM public.daily_rollups`
    }
  }
  */

  /*
  preAggregations: {
    rollupMinute: {
      type: `originalSql`,
      sql: `SELECT ts_minute as ts, target_id, mean_rtt, highest_rtt, packet_loss_rate FROM public.minute_rollups`
    },
    rollupHourly: {
      type: `originalSql`,
      sql: `SELECT ts_hour as ts, target_id, mean_rtt, highest_rtt, packet_loss_rate FROM public.hourly_rollups`
    },
    rollupDaily: {
      type: `originalSql`,
      sql: `SELECT ts_day as ts, target_id, mean_rtt, highest_rtt, packet_loss_rate FROM public.daily_rollups`
    }
  }
  */
});
