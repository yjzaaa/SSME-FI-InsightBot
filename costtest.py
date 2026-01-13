from modules.CostAnalyst import test_excel_sql_specialist_agent,sqlQuery,generate_cost_rate_sql,calculate_monthly_cost_table,caculate_yearly_cost
import os 
import asyncio  

if __name__ == "__main__":
    # asyncio.run(test_excel_sql_specialist_agent())
    # 2026-01-09 13:42:44,359 [DEBUG] autogen_agentchat.events: source='excel_sql_specialist' models_usage=RequestUsage(prompt_tokens=3667, completion_tokens=502) metadata={} content=[FunctionCall(id='call_OfgmI4feOwXJE0AHvaODKhGT', arguments='{"file_path": "Data/Function cost allocation analysis to IT 20260104.xlsx", "query": '
    # '"SELECT cdb.`Month`, SUM(COALESCE(t7.`RateNo`, 0)) AS `rate`, cdb.`Amount` AS `amount` FROM CostDataBase cdb LEFT JOIN Table7 t7 ON cdb.`Month` = t7.`Month` AND cdb.`Year` = t7.`Year` AND cdb.`Scenario` = t7.`Scenario` AND cdb.`Key` = t7.`Key` WHERE cdb.`Year` = \'FY25\' AND cdb.`Scenario` = \'Actual\' AND cdb.`Function` = \'HR Allocation\' AND cdb.`Key` = \'480055 Cycle\' AND t7.`Year` = \'FY25\' AND t7.`Scenario` = \'Actual\' AND t7.`Key` = \'480055 Cycle\' AND t7.`CC` = \'XP\' GROUP BY cdb.`Month`, cdb.`Amount` ORDER BY cdb.`Month`'
    # '", "sql_table_names": ["CostDataBase", "Table7"]}', name='sqlQuery'), FunctionCall(id='call_3EwZQV37pKTEMbkQE75x1EGr', arguments='{"file_path": "Data/Function cost allocation analysis to IT 20260104.xlsx", "query": "SELECT cdb.`Month`, SUM(COALESCE(t7.`RateNo`, 0)) AS `rate`, cdb.`Amount` AS `amount` FROM CostDataBase cdb LEFT JOIN Table7 t7 ON cdb.`Month` = t7.`Month` AND cdb.`Year` = t7.`Year` AND cdb.`Scenario` = t7.`Scenario` AND cdb.`Key` = t7.`Key` WHERE cdb.`Year` = \'FY26\' AND cdb.`Scenario` = \'Budget1\' AND cdb.`Function` = \'HR Allocation\' AND cdb.`Key` = \'480055 Cycle\' AND t7.`Year` = \'FY26\' AND t7.`Scenario` = \'Budget1\' AND t7.`Key` = \'480055 Cycle\' AND t7.`CC` = \'413001\' GROUP BY cdb.`Month`, cdb.`Amount` ORDER BY cdb.`Month`", "sql_table_names": ["CostDataBase", "Table7"]}', name='sqlQuery')] type='ToolCallRequestEvent'

    # print(sqlQuery(
    #     file_path="back_end_code/Data/Function cost allocation analysis to IT 20260104.xlsx",
    #     # query="SELECT " \
    #     # "cdb.`Month`," \
    #     # " SUM(COALESCE(t7.`RateNo`, 0)) AS `rate`, " \
    #     # "cdb.`Amount` AS `amount`" \
    #     # " FROM CostDataBase cdb " \
    #     # "LEFT JOIN Table7 t7 " \
    #     # "ON cdb.`Month` = t7.`Month` " \
    #     # "AND cdb.`Year` = t7.`Year`" \
    #     # " AND cdb.`Scenario` = t7.`Scenario` " \
    #     # "AND cdb.`Key` = t7.`Key` " \
    #     # "WHERE cdb.`Year` = 'FY25' " \
    #     # "AND cdb.`Scenario` = 'Actual' " \
    #     # "AND cdb.`Function` = 'HR Allocation' " \
    #     # "AND cdb.`Key` = '480055 Cycle' " \
    #     # "AND t7.`Year` = 'FY25' " \
    #     # # "AND t7.`Scenario` = 'Actual' " \
    #     # "AND t7.`Key` = '480055 Cycle' " \
    #     # "AND t7.`CC` = '413011' " \
    #     # "GROUP BY cdb.`Month`, cdb.`Amount` " \
    #     # "ORDER BY cdb.`Month`",
    #       query="SELECT " \
    #     "cdb.`Month`," \
    #     " SUM(COALESCE(t7.`RateNo`, 0)) AS `rate`, " \
    #     "cdb.`Amount` AS `amount`" \
    #     " FROM CostDataBase cdb " \
    #     "LEFT JOIN Table7 t7 " \
    #     "ON cdb.`Month` = t7.`Month` " \
    #     "AND cdb.`Year` = t7.`Year`" \
    #     " AND cdb.`Scenario` = t7.`Scenario` " \
    #     "AND cdb.`Key` = t7.`Key` " \
    #     "WHERE cdb.`Year` = 'FY25' " \
    #     "AND cdb.`Scenario` = 'Actual' " \
    #     "AND cdb.`Function` = 'IT Allocation' " \
    #     "AND cdb.`Key` = '480056 Cycle' " \
    #     "AND t7.`bl` = 'CT' " \
    #     "GROUP BY cdb.`Month`, cdb.`Amount` " \
    #     "ORDER BY cdb.`Month`",
    #     sql_table_names=["CostDataBase", "Table7"]
    # ))
    # [-411451.26,-1039171.3,-984574.59,-570027.95,-681500.75,-278466.77,-896034.36,-834138.34,-605203.31,-792210.13,0.0,-754354.64]
    print(caculate_yearly_cost([-411451.26,-1039171.3,-984574.59,-570027.95,-681500.75,-278466.77,-896034.36,-834138.34,-605203.31,-792210.13,0.0,-754354.64]))
    # print(sqlQuery(
    #     file_path="back_end_code/Data/Function cost allocation analysis to IT 20260104.xlsx",
    #     query=generate_cost_rate_sql("FY25", "Budget1"),
    #     sql_table_names=["CostDataBase", "Table7"]
    # ))