read_model -i "snapshots/canonical.smv"
go
check_ctlspec -p "EF (state = BIND & EF (state = EXECUTE_MEASURE & EF (state = COMPUTE_ENERGY & EF (state = CHECK_STOP & EF (state = OPTIMIZER_STEP & EF (state = DONE))))))"
check_ctlspec -p "EF (state = ABORT)"
quit
