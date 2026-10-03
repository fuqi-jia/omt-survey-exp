; benchmark generated from python API
(set-info :status unknown)
(declare-fun x () (_ FloatingPoint 11 53))
(declare-fun r () (_ FloatingPoint 11 53))
(assert
 (= x (fp (_ bv1 1) (_ bv1397 11) (_ bv3746490461901976 52))))
(assert
 (= (fp.abs x) r))
(assert
 (let ((?x24 (fp (_ bv0 1) (_ bv1397 11) (_ bv3746490461901976 52))))
(fp.lt r ?x24)))
(check-sat)
