10 FOR I = 1 TO 100000
15 LET Q$ = INKEY$
17 PRINT "Q$";Q$
20 IF Q$ = "Q" THEN GOSUB 100
24 IF INKEY$ = "G" THEN GOSUB 300
30 NEXT I
100 PRINT "Q ";I
120 RETURN
300 PRINT "INKEY IN THE IF DIRETLY"
310 RETURN





























































































