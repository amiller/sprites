pragma solidity ^0.4.3;

contract PreimageManager {
    mapping ( bytes32 => uint ) timestamp;
    function submitPreimage(bytes32 x) {
	if (timestamp[sha3(x)] == 0)
	    timestamp[sha3(x)] = block.number;
    }

    function revealedBefore(bytes32 h, uint T) returns(bool) {
	uint t = timestamp[h];
	return (t > 0 && t <= T);
    }
}
