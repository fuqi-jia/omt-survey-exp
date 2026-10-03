; benchmark generated from python API
(set-info :status unknown)
(declare-fun x () (_ FloatingPoint 11 53))
(declare-fun y () (_ FloatingPoint 11 53))
(declare-fun r () (_ FloatingPoint 11 53))
(assert
 (fp.leq x (fp (_ bv1 1) (_ bv1694 11) (_ bv1639087830226334 52))))
(assert
 (fp.leq y (fp (_ bv0 1) (_ bv450 11) (_ bv3468604031872236 52))))
(assert
 (= (fp.add roundTowardZero x y) r))
(assert
 (let ((?x31 (fp (_ bv1 1) (_ bv1694 11) (_ bv1639087830226333 52))))
(fp.gt r ?x31)))
(check-sat)
