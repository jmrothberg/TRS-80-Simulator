110 LET X=10
140 PRINT "String operations:"
150 LET A$ = "HELLO"
160 LET B$ = "WORLD"
170 PRINT A$ + " " + B$
180 PRINT "THE LINE ABOVE SHOULD BE HELLO WORLD"
640 PRINT "Combined string and numeric operations:"
650 PRINT A$ + STR$(X) + B$
660 PRINT "THE LINE ABOVE SHOULD BE HELLO10WORLD"
670 PRINT "Function with string literal: " + CHR$(65) + " is A"
680 PRINT "THE LINE ABOVE SHOULD BE Function with string literal: A is A"
690 PRINT "Nested functions with string: " + CHR$(INT(RND * 26) + 65) + " random"
700 PRINT "THE LINE ABOVE SHOULD SHOW A RANDOM UPPERCASE LETTER BETWEEN Function with string: and random"
710 PRINT "END OF TESTS"


