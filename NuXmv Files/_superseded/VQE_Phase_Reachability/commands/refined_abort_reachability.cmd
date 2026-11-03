read_model -i "snapshots/refined_abort.smv"
go
check_fsm
print_reachable_states
check_ctlspec -p "EF (state = BIND)"
check_ctlspec -p "EF (state = EXECUTE_MEASURE)"
check_ctlspec -p "EF (state = COMPUTE_ENERGY)"
check_ctlspec -p "EF (state = CHECK_STOP)"
check_ctlspec -p "EF (state = OPTIMIZER_STEP)"
check_ctlspec -p "EF (state = DONE)"
check_compute -p "MIN [state = S_INIT, state = BIND]"
check_compute -p "MIN [state = S_INIT, state = EXECUTE_MEASURE]"
check_compute -p "MIN [state = S_INIT, state = COMPUTE_ENERGY]"
check_compute -p "MIN [state = S_INIT, state = CHECK_STOP]"
check_compute -p "MIN [state = S_INIT, state = OPTIMIZER_STEP]"
check_compute -p "MIN [state = S_INIT, state = DONE]"
quit
