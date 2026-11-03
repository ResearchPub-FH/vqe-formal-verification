read_model -i "snapshots/baseline.smv"
go
check_ctlspec -p "AG !(state = BIND)"
check_ctlspec -p "AG !(state = EXECUTE_MEASURE)"
check_ctlspec -p "AG !(state = COMPUTE_ENERGY)"
check_ctlspec -p "AG !(state = CHECK_STOP)"
check_ctlspec -p "AG !(state = OPTIMIZER_STEP)"
check_ctlspec -p "AG !(state = DONE)"
check_ctlspec -p "AG !(state = DONE & iter > 0)"
quit
