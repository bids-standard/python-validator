function results = bids_validate_file(filepaths)

% this is a Matlab wrapper that calls the BIDS validator python version to validate a file
% make sure this is installed in your python environment: python -m pip install bids_validator
% 
% INPUT:
% filepaths can be a string array: ["/sub-01/anat/sub-01_rec-CSD_T1w.nii.gz", "/sub-01/anat/sub-01_acq-23_rec-CSD_T1w.json"]
% filepaths can be a cell array:   {"/sub-01/anat/sub-01_rec-CSD_T1w.nii.gz", "/sub-01/anat/sub-01_acq-23_rec-CSD_T1w.json"}
% filepaths can be a single file:  "/sub-01/anat/sub-01_rec-CSD_T1w.nii.gz"
%
% OUTPUT:
% returns a logical array indicating whether each file is BIDS-compliant
%
% Cyril Pernet 08-10-2025

    % Check if Python is available
    try
        pyenv;
    catch
        error('Python environment not available. Please configure Python for MATLAB using pyenv.');
    end
    
    % Ensure filepaths is a cell array
    if ischar(filepaths)
        % Single character string
        filepaths = {filepaths};
    elseif isstring(filepaths)
        % String array - convert to cell array
        filepaths = cellstr(filepaths);
    elseif iscell(filepaths)
        % Already a cell array - ensure all elements are char
        filepaths = cellfun(@char, filepaths, 'UniformOutput', false);
    else
        error('filepaths must be a char, string array, or cell array of filenames');
    end
    
    % Initialize results array
    results = false(length(filepaths), 1);
    
    try
        % Import and initialize the BIDS validator
        pyrun("from bids_validator import BIDSValidator");
        pyrun("validator = BIDSValidator()");
        
        % Validate each file
        for i = 1:length(filepaths)
            filepath = filepaths{i};
            
            % Use pyrun to call the validator
            result = pyrun("result = validator.is_bids(filepath)", "result", filepath=filepath);
            results(i) = logical(result);
            
            % Display result
            fprintf('File: %s -> BIDS valid: %s\n', filepath, string(results(i)));
        end
        
    catch ME
        if contains(ME.message, 'bids_validator')
            error(['BIDS validator not found. Please install it using:\n' ...
                   'python -m pip install bids_validator\n' ...
                   'Original error: %s'], ME.message);
        else
            rethrow(ME);
        end
    end

